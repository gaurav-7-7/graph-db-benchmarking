#!/usr/bin/env python3
"""
analysis/generate_report.py — Read raw CSVs and generate charts + summary tables
==================================================================================
Usage:
    python analysis/generate_report.py --seq results/raw/sequential_results_YYYYMMDD.csv \
                                        --mixed results/raw/mixed_workload_YYYYMMDD.csv \
                                        --out results/charts
"""

import argparse
import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
import seaborn as sns
from tabulate import tabulate

# ── Style ─────────────────────────────────────────────────────────────────────

PALETTE = {
    "CognoDB":      "#6C63FF",  # Purple
    "Neo4j AuraDB": "#00BFA5",  # Teal
    "Memgraph":     "#FF6B6B",  # Coral
    "FalkorDB":     "#FFD166",  # Amber
    "ArangoDB":     "#4ECDC4",  # Mint
}

plt.rcParams.update({
    "figure.facecolor": "#0F1117",
    "axes.facecolor":   "#1A1D2E",
    "axes.edgecolor":   "#2E3250",
    "axes.labelcolor":  "#C9D1D9",
    "text.color":       "#C9D1D9",
    "xtick.color":      "#8B949E",
    "ytick.color":      "#8B949E",
    "grid.color":       "#21262D",
    "font.family":      "sans-serif",
    "font.size":        11,
    "axes.titlesize":   13,
    "axes.titleweight": "bold",
    "axes.grid":        True,
    "grid.linewidth":   0.5,
    "figure.dpi":       150,
})


def load_data(seq_csv: Path, mixed_csv: Path):
    seq = pd.read_csv(seq_csv)
    mixed = pd.read_csv(mixed_csv)
    return seq, mixed


# ── Chart 1: Traversal latency (p50 + p95) ───────────────────────────────────

def chart_traversal_latency(seq: pd.DataFrame, out_dir: Path) -> None:
    hops = ["Traversal 1-hop", "Traversal 2-hop", "Traversal 3-hop"]
    df = seq[seq["benchmark"].isin(hops)].copy()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Traversal Latency by Hop Depth", color="white", fontsize=15, y=1.02)

    for ax, metric, label in zip(axes, ["p50_ms", "p95_ms"], ["p50 Latency", "p95 Latency"]):
        pivot = df.pivot(index="benchmark", columns="db", values=metric)
        pivot = pivot.reindex(hops)
        pivot.plot(kind="bar", ax=ax, color=[PALETTE.get(c, "#888") for c in pivot.columns],
                   width=0.7, edgecolor="none")
        ax.set_title(label)
        ax.set_xlabel("")
        ax.set_ylabel("Latency (ms)")
        ax.set_xticklabels(["1-hop", "2-hop", "3-hop"], rotation=0)
        ax.legend(loc="upper left", fontsize=9)
        ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.0f"))

    fig.tight_layout()
    out_path = out_dir / "traversal_latency.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {out_path}")
    plt.close(fig)


# ── Chart 2: Lookup + Aggregation latency ────────────────────────────────────

def chart_lookup_aggregation(seq: pd.DataFrame, out_dir: Path) -> None:
    benches = ["Point lookup (by user_id)", "Filtered lookup (age > 25 AND gender=1)",
               "Aggregation (count follows by gender)"]
    df = seq[seq["benchmark"].isin(benches)].copy()
    short_names = {
        "Point lookup (by user_id)": "Point Lookup",
        "Filtered lookup (age > 25 AND gender=1)": "Filtered Lookup",
        "Aggregation (count follows by gender)": "Aggregation",
    }
    df["benchmark"] = df["benchmark"].map(short_names)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Lookup & Aggregation Latency", color="white", fontsize=15, y=1.02)

    for ax, metric, label in zip(axes, ["p50_ms", "p95_ms"], ["p50 Latency", "p95 Latency"]):
        pivot = df.pivot(index="benchmark", columns="db", values=metric)
        pivot.plot(kind="bar", ax=ax, color=[PALETTE.get(c, "#888") for c in pivot.columns],
                   width=0.7, edgecolor="none")
        ax.set_title(label)
        ax.set_xlabel("")
        ax.set_ylabel("Latency (ms)")
        ax.set_xticklabels(pivot.index, rotation=15, ha="right")
        ax.legend(loc="upper left", fontsize=9)

    fig.tight_layout()
    out_path = out_dir / "lookup_aggregation.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {out_path}")
    plt.close(fig)


# ── Chart 3: Mixed workload QPS by concurrency ───────────────────────────────

def chart_mixed_workload(mixed: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle("Mixed Workload Throughput (70% Read / 30% Write)", color="white", fontsize=15)

    for db_name, group in mixed.groupby("db"):
        group = group.sort_values("concurrency")
        ax.plot(group["concurrency"], group["qps"],
                marker="o", label=db_name, color=PALETTE.get(db_name, "#888"),
                linewidth=2, markersize=8)

    ax.set_xlabel("Concurrent Clients")
    ax.set_ylabel("Queries / Second")
    ax.set_xticks(sorted(mixed["concurrency"].unique()))
    ax.legend(loc="upper left", fontsize=10)
    ax.set_title("Throughput vs. Concurrency")

    fig.tight_layout()
    out_path = out_dir / "mixed_workload_qps.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {out_path}")
    plt.close(fig)


# ── Chart 4: Heatmap — all benchmarks ────────────────────────────────────────

def chart_heatmap(seq: pd.DataFrame, out_dir: Path) -> None:
    pivot = seq.pivot(index="benchmark", columns="db", values="p50_ms")
    # Normalize per row (relative performance)
    pivot_norm = pivot.div(pivot.min(axis=1), axis=0)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(
        pivot_norm, annot=pivot.round(1), fmt=".1f",
        cmap="RdYlGn_r", ax=ax, linewidths=0.5,
        annot_kws={"size": 9}, cbar_kws={"label": "Relative to fastest (lower=better)"},
    )
    ax.set_title("p50 Latency Heatmap (ms) — normalized to fastest", pad=15)
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.xticks(rotation=20, ha="right")
    plt.yticks(rotation=0)

    fig.tight_layout()
    out_path = out_dir / "heatmap_p50.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor="#1A1D2E")
    print(f"  Saved: {out_path}")
    plt.close(fig)


# ── Print summary tables ──────────────────────────────────────────────────────

def print_tables(seq: pd.DataFrame, mixed: pd.DataFrame) -> None:
    print("\n" + "═" * 80)
    print("  SEQUENTIAL BENCHMARKS — p50 / p95 (ms)")
    print("═" * 80)
    pivot_p50 = seq.pivot(index="benchmark", columns="db", values="p50_ms").round(2)
    pivot_p95 = seq.pivot(index="benchmark", columns="db", values="p95_ms").round(2)
    print("\n  p50 Latency (ms):")
    print(tabulate(pivot_p50, headers="keys", tablefmt="github", floatfmt=".2f"))
    print("\n  p95 Latency (ms):")
    print(tabulate(pivot_p95, headers="keys", tablefmt="github", floatfmt=".2f"))

    print("\n" + "═" * 80)
    print("  MIXED WORKLOAD — QPS by concurrency")
    print("═" * 80)
    pivot_qps = mixed.pivot(index="concurrency", columns="db", values="qps").round(1)
    print(tabulate(pivot_qps, headers="keys", tablefmt="github", floatfmt=".1f"))


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seq", required=True, type=Path, help="Sequential results CSV")
    parser.add_argument("--mixed", required=True, type=Path, help="Mixed workload CSV")
    parser.add_argument("--out", type=Path, default=Path("results/charts"),
                        help="Output directory for charts")
    return parser.parse_args()


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"Loading: {args.seq}")
    print(f"Loading: {args.mixed}")
    seq, mixed = load_data(args.seq, args.mixed)

    print("\nGenerating charts ...")
    chart_traversal_latency(seq, args.out)
    chart_lookup_aggregation(seq, args.out)
    chart_mixed_workload(mixed, args.out)
    chart_heatmap(seq, args.out)

    print_tables(seq, mixed)

    print(f"\n✅  Charts saved to: {args.out}")


if __name__ == "__main__":
    main()
