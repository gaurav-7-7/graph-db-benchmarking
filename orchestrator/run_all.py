#!/usr/bin/env python3
"""
orchestrator/run_all.py — Master benchmark orchestrator
=======================================================
Single entrypoint to load data and run all benchmarks across all databases.

Usage:
    python orchestrator/run_all.py --phase load          # Load data only
    python orchestrator/run_all.py --phase bench         # Benchmark only
    python orchestrator/run_all.py --phase all           # Load + benchmark
    python orchestrator/run_all.py --phase bench --db cognodb  # Single DB

Options:
    --db       all | cognodb | auradb | memgraph | falkordb | arango
    --phase    all | load | bench
    --iters    Benchmark iterations per query (default: 100)
    --warmup   Warm-up iterations (default: 10)
    --sample   Traversal start node sample size (default: 50)
    --duration Mixed workload duration in seconds (default: 30)
    --out      Output directory for results CSVs (default: results/raw)
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.base_runner import save_stats_csv
from benchmarks.neo4j_runner import Neo4jRunner
from benchmarks.arango_runner import ArangoRunner
from benchmarks.mixed_workload import run_mixed_workload, arango_mixed_workload
from loaders.neo4j_loader import Neo4jLoader
from loaders.arango_loader import ArangoLoader

NODES_CSV = ROOT / "data" / "nodes.csv"
EDGES_CSV = ROOT / "data" / "edges.csv"
RESULTS_DIR = ROOT / "results" / "raw"


# ── DB registry ───────────────────────────────────────────────────────────────

ALL_DBS = ["cognodb", "auradb", "memgraph", "falkordb", "arango"]


def get_runner(db: str, iters: int, warmup: int, sample: int) -> "BaseRunner":
    kwargs = dict(iterations=iters, warmup=warmup, traversal_sample_size=sample)
    if db == "cognodb":
        return Neo4jRunner.for_cognodb(**kwargs)
    elif db == "auradb":
        return Neo4jRunner.for_auradb(**kwargs)
    elif db == "memgraph":
        return Neo4jRunner.for_memgraph(**kwargs)
    elif db == "falkordb":
        return Neo4jRunner.for_falkordb(**kwargs)
    elif db == "arango":
        return ArangoRunner(**kwargs)
    else:
        raise ValueError(f"Unknown DB: {db}")


def get_loader(db: str) -> "BaseLoader":
    if db in ("cognodb", "auradb", "memgraph", "falkordb"):
        factory = {
            "cognodb": Neo4jLoader.for_cognodb,
            "auradb": Neo4jLoader.for_auradb,
            "memgraph": Neo4jLoader.for_memgraph,
            "falkordb": Neo4jLoader.for_falkordb,
        }[db]
        return factory(NODES_CSV, EDGES_CSV)
    elif db == "arango":
        return ArangoLoader(NODES_CSV, EDGES_CSV)
    else:
        raise ValueError(f"Unknown DB: {db}")


# ── Load phase ────────────────────────────────────────────────────────────────

def run_load(dbs: list[str], out_dir: Path) -> None:
    load_results = []
    for db in dbs:
        print(f"\n{'─'*60}")
        print(f"  Loading data → {db.upper()}")
        print(f"{'─'*60}")
        try:
            loader = get_loader(db)
            result = loader.run()
            load_results.append({
                "db": result.db_name,
                "node_count": result.node_count,
                "edge_count": result.edge_count,
                "total_seconds": round(result.total_seconds, 2),
                "nodes_per_second": round(result.nodes_per_second, 0),
                "edges_per_second": round(result.edges_per_second, 0),
            })
        except Exception as e:
            print(f"  ERROR loading {db}: {e}")
            load_results.append({"db": db, "error": str(e)})

    # Save load results
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    load_csv = out_dir / f"load_results_{ts}.csv"
    with open(load_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["db", "node_count", "edge_count",
                           "total_seconds", "nodes_per_second", "edges_per_second", "error"]
        )
        writer.writeheader()
        for row in load_results:
            writer.writerow({**{"error": ""}, **row})

    print(f"\nLoad results → {load_csv}")


# ── Benchmark phase ───────────────────────────────────────────────────────────

def run_bench(dbs: list[str], iters: int, warmup: int, sample: int,
              duration: int, out_dir: Path) -> None:
    all_sequential = {}   # db -> { bench_name -> Stats }
    all_mixed = []        # list[MixedWorkloadResult]

    for db in dbs:
        print(f"\n{'═'*60}")
        print(f"  BENCHMARKING: {db.upper()}")
        print(f"{'═'*60}")
        try:
            runner = get_runner(db, iters, warmup, sample)
            runner.connect()

            # Sequential benchmarks
            seq_results = runner.run_all_sequential()
            all_sequential[db] = seq_results

            # Mixed workload
            print(f"\n  [{db}] Running mixed workload ...")
            concurrency_levels = [
                int(x) for x in os.environ.get("MIXED_CONCURRENCY", "1,10,40").split(",")
            ]
            if db == "arango":
                mixed = arango_mixed_workload(
                    runner, concurrency_levels=concurrency_levels,
                    duration_seconds=duration
                )
            else:
                mixed = run_mixed_workload(
                    runner, concurrency_levels=concurrency_levels,
                    duration_seconds=duration
                )
            all_mixed.extend(mixed)

            runner.close()
        except Exception as e:
            print(f"  ERROR benchmarking {db}: {e}")
            import traceback
            traceback.print_exc()

    # ── Save sequential results ────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    seq_csv = out_dir / f"sequential_results_{ts}.csv"
    save_stats_csv(all_sequential, seq_csv)

    # ── Save mixed workload results ────────────────────────────────────────────
    mixed_csv = out_dir / f"mixed_workload_{ts}.csv"
    with open(mixed_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "db", "concurrency", "duration_seconds",
            "total_queries", "read_queries", "write_queries",
            "qps", "read_qps", "write_qps", "errors"
        ])
        writer.writeheader()
        for r in all_mixed:
            writer.writerow({
                "db": r.db_name,
                "concurrency": r.concurrency,
                "duration_seconds": r.duration_seconds,
                "total_queries": r.total_queries,
                "read_queries": r.read_queries,
                "write_queries": r.write_queries,
                "qps": round(r.qps, 2),
                "read_qps": round(r.read_qps, 2),
                "write_qps": round(r.write_qps, 2),
                "errors": r.errors,
            })

    print(f"\nMixed workload results → {mixed_csv}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Graph DB Benchmark Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default="all",
                        help="DB to benchmark: all | cognodb | auradb | memgraph | falkordb | arango")
    parser.add_argument("--phase", default="all", choices=["all", "load", "bench"],
                        help="Which phase to run (default: all)")
    parser.add_argument("--iters", type=int, default=100,
                        help="Benchmark iterations per query (default: 100)")
    parser.add_argument("--warmup", type=int, default=10,
                        help="Warm-up iterations (default: 10)")
    parser.add_argument("--sample", type=int, default=50,
                        help="Traversal start node sample size (default: 50)")
    parser.add_argument("--duration", type=int, default=30,
                        help="Mixed workload duration in seconds (default: 30)")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR,
                        help="Output directory for results CSVs")
    return parser.parse_args()


def main():
    args = parse_args()

    if not NODES_CSV.exists() or not EDGES_CSV.exists():
        print("ERROR: Dataset not found. Run: bash data/download.sh && python data/sample.py")
        sys.exit(1)

    dbs = ALL_DBS if args.db == "all" else [args.db]

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     Graph DB Benchmark Suite                             ║
╠══════════════════════════════════════════════════════════╣
║  Phase      : {args.phase:<42} ║
║  Databases  : {', '.join(dbs):<42} ║
║  Iterations : {args.iters:<42} ║
║  Warm-up    : {args.warmup:<42} ║
║  Sample     : {args.sample:<42} ║
║  Duration   : {args.duration}s{'':<40} ║
╚══════════════════════════════════════════════════════════╝
""")

    t_start = time.perf_counter()

    if args.phase in ("all", "load"):
        run_load(dbs, args.out)

    if args.phase in ("all", "bench"):
        run_bench(dbs, args.iters, args.warmup, args.sample, args.duration, args.out)

    elapsed = time.perf_counter() - t_start
    print(f"\n✅  Done in {elapsed:.1f}s. Results in: {args.out}")


if __name__ == "__main__":
    main()
