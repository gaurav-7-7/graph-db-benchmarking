#!/usr/bin/env python3
"""
data/sample.py — Reproducible sampling of the SNAP soc-Pokec dataset
=====================================================================
Reads the full Pokec relationship + profile files and produces:
  - data/nodes.csv      (sampled users with attributes)
  - data/edges.csv      (sampled directed FOLLOWS relationships)

Target size: ~250k nodes, ~500k relationships
Keeps the induced subgraph of the sampled nodes (all edges between
sampled nodes) so that graph structure is realistic, not random.

Usage:
    python data/sample.py [--nodes 250000] [--seed 42]
"""

import argparse
import csv
import os
import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
RAW_DIR = SCRIPT_DIR / "raw"

RELATIONSHIPS_FILE = RAW_DIR / "soc-pokec-relationships.txt"
PROFILES_FILE = RAW_DIR / "soc-pokec-profiles.txt"

OUTPUT_NODES = SCRIPT_DIR / "nodes.csv"
OUTPUT_EDGES = SCRIPT_DIR / "edges.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Sample the Pokec dataset")
    parser.add_argument("--nodes", type=int, default=250_000,
                        help="Number of nodes to sample (default: 250000)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    return parser.parse_args()


def load_all_node_ids(profiles_path: Path) -> list[int]:
    """Return all user IDs from the profiles file."""
    node_ids = []
    print(f"  Reading profile IDs from {profiles_path.name} ...")
    with open(profiles_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if parts and parts[0].isdigit():
                node_ids.append(int(parts[0]))
    return node_ids


def load_profile_attributes(profiles_path: Path, sampled_ids: set[int]) -> dict[int, dict]:
    """
    Load a subset of profile attributes for sampled nodes.
    Pokec profile columns (tab-separated, no header):
      0: user_id, 1: public, 2: completion_percentage,
      3: gender, 4: region, 5: last_login, 6: registration,
      7: AGE, ...
    We keep: user_id, gender, age, region
    """
    profiles = {}
    with open(profiles_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if not parts or not parts[0].isdigit():
                continue
            uid = int(parts[0])
            if uid not in sampled_ids:
                continue
            profiles[uid] = {
                "user_id": uid,
                "gender": parts[3] if len(parts) > 3 else "null",
                "age": parts[7] if len(parts) > 7 else "null",
                "region": parts[4] if len(parts) > 4 else "null",
            }
    return profiles


def sample_induced_edges(
    relationships_path: Path,
    sampled_ids: set[int],
    max_edges: int = 600_000,
) -> list[tuple[int, int]]:
    """
    Load all edges where BOTH endpoints are in sampled_ids.
    Cap at max_edges to stay within free-tier storage.
    """
    edges = []
    print(f"  Scanning relationships from {relationships_path.name} ...")
    with open(relationships_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            src, dst = int(parts[0]), int(parts[1])
            if src in sampled_ids and dst in sampled_ids:
                edges.append((src, dst))
                if len(edges) >= max_edges:
                    print(f"  Edge cap ({max_edges:,}) reached — stopping scan.")
                    break
    return edges


def write_nodes_csv(profiles: dict[int, dict], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "gender", "age", "region"])
        writer.writeheader()
        for profile in profiles.values():
            writer.writerow(profile)
    print(f"  Wrote {len(profiles):,} nodes → {output_path}")


def write_edges_csv(edges: list[tuple[int, int]], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["src_id", "dst_id"])
        writer.writerows(edges)
    print(f"  Wrote {len(edges):,} edges → {output_path}")


def main():
    args = parse_args()
    random.seed(args.seed)

    if not RELATIONSHIPS_FILE.exists() or not PROFILES_FILE.exists():
        print("ERROR: Raw files not found. Run: bash data/download.sh first.")
        sys.exit(1)

    print(f"\n[1/5] Loading all node IDs (seed={args.seed}) ...")
    all_ids = load_all_node_ids(PROFILES_FILE)
    print(f"  Total nodes in full dataset: {len(all_ids):,}")

    print(f"\n[2/5] Sampling {args.nodes:,} nodes ...")
    sampled_ids = set(random.sample(all_ids, min(args.nodes, len(all_ids))))
    print(f"  Sampled: {len(sampled_ids):,} nodes")

    print(f"\n[3/5] Loading profile attributes for sampled nodes ...")
    profiles = load_profile_attributes(PROFILES_FILE, sampled_ids)
    print(f"  Profiles loaded: {len(profiles):,}")

    print(f"\n[4/5] Extracting induced subgraph edges ...")
    edges = sample_induced_edges(RELATIONSHIPS_FILE, sampled_ids)
    print(f"  Edges in induced subgraph: {len(edges):,}")

    print(f"\n[5/5] Writing output CSVs ...")
    write_nodes_csv(profiles, OUTPUT_NODES)
    write_edges_csv(edges, OUTPUT_EDGES)

    print(f"""
=============================================================
  Dataset Summary
=============================================================
  Nodes  : {len(profiles):,}
  Edges  : {len(edges):,}
  Seed   : {args.seed}
  Node CSV : {OUTPUT_NODES}
  Edge CSV : {OUTPUT_EDGES}
=============================================================
  Next: python orchestrator/run_all.py --db all --phase load
""")


if __name__ == "__main__":
    main()
