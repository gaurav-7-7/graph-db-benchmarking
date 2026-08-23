#!/usr/bin/env python3
"""
benchmarks/base_runner.py — Abstract benchmark runner + stats engine
=====================================================================

Subclasses implement:
  - connect() / close()
  - run_query(cypher_or_aql, params) -> None   (executes, discards result)
  - get_sample_node_ids(n) -> list[int]

The base class provides:
  - measure(query_fn, iterations, warmup) -> Stats
  - run_all() -> dict[str, Stats]               (calls all metric methods)
"""

import csv
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable


# ── Stats dataclass ───────────────────────────────────────────────────────────

@dataclass
class Stats:
    """Latency statistics for a single benchmark category."""
    name: str
    db_name: str
    iterations: int
    p50_ms: float
    p95_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    raw_ms: list[float] = field(default_factory=list, repr=False)

    def summary_line(self) -> str:
        return (
            f"  [{self.db_name}] {self.name:40s} "
            f"p50={self.p50_ms:7.2f}ms  p95={self.p95_ms:7.2f}ms  "
            f"mean={self.mean_ms:7.2f}ms  (n={self.iterations})"
        )


def compute_stats(name: str, db_name: str, latencies_ms: list[float]) -> Stats:
    n = len(latencies_ms)
    sorted_ms = sorted(latencies_ms)
    return Stats(
        name=name,
        db_name=db_name,
        iterations=n,
        p50_ms=statistics.median(sorted_ms),
        p95_ms=sorted_ms[int(0.95 * n)],
        mean_ms=statistics.mean(sorted_ms),
        min_ms=sorted_ms[0],
        max_ms=sorted_ms[-1],
        raw_ms=latencies_ms,
    )


# ── Abstract runner ────────────────────────────────────────────────────────────

class BaseRunner(ABC):
    """
    Abstract benchmark runner. One subclass per database.
    """

    DB_NAME: str = "unknown"

    def __init__(
        self,
        iterations: int = 100,
        warmup: int = 10,
        traversal_sample_size: int = 50,
        random_seed: int = 42,
    ):
        self.iterations = iterations
        self.warmup = warmup
        self.traversal_sample_size = traversal_sample_size
        self.random_seed = random_seed
        self._sample_node_ids: list[int] = []

    # ── To implement ──────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """Establish connection."""

    @abstractmethod
    def close(self) -> None:
        """Close connection."""

    @abstractmethod
    def execute(self, query: str, params: dict | None = None) -> list[dict]:
        """Run a query and return results as list of dicts."""

    @abstractmethod
    def fetch_sample_node_ids(self, n: int, seed: int) -> list[int]:
        """Return n random node IDs from the DB (for traversal start nodes)."""

    # ── Measurement engine ────────────────────────────────────────────────────

    def measure(
        self,
        name: str,
        query_fn: Callable[[], None],
        iterations: int | None = None,
        warmup: int | None = None,
    ) -> Stats:
        """
        Time `query_fn()` for `warmup` + `iterations` calls.
        Returns Stats computed only over the measurement iterations.
        """
        iters = iterations or self.iterations
        wu = warmup or self.warmup

        # Warm-up (discarded)
        for _ in range(wu):
            query_fn()

        # Measurement
        latencies: list[float] = []
        for _ in range(iters):
            t0 = time.perf_counter()
            query_fn()
            latencies.append((time.perf_counter() - t0) * 1000)  # ms

        s = compute_stats(name, self.DB_NAME, latencies)
        print(s.summary_line())
        return s

    def _get_sample_ids(self) -> list[int]:
        if not self._sample_node_ids:
            self._sample_node_ids = self.fetch_sample_node_ids(
                self.traversal_sample_size, self.random_seed
            )
        return self._sample_node_ids

    # ── Benchmark methods (override to add DB-specific queries) ───────────────

    def bench_1hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    "MATCH (n:User {user_id: $id})-[:FOLLOWS]->(m) RETURN count(m) AS cnt",
                    {"id": nid},
                )
            s = self.measure(f"1-hop traversal (node {node_id})", q, iterations=self.iterations // len(ids) or 1, warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 1-hop", self.DB_NAME, latencies)

    def bench_2hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    "MATCH (n:User {user_id: $id})-[:FOLLOWS*2]->(m) RETURN count(m) AS cnt",
                    {"id": nid},
                )
            s = self.measure(f"2-hop traversal (node {node_id})", q, iterations=max(self.iterations // len(ids), 1), warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 2-hop", self.DB_NAME, latencies)

    def bench_3hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    "MATCH (n:User {user_id: $id})-[:FOLLOWS*3]->(m) RETURN count(m) AS cnt",
                    {"id": nid},
                )
            s = self.measure(f"3-hop traversal (node {node_id})", q, iterations=max(self.iterations // len(ids), 1), warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 3-hop", self.DB_NAME, latencies)

    def bench_point_lookup(self) -> Stats:
        ids = self._get_sample_ids()
        import random
        rng = random.Random(self.random_seed)
        lookup_ids = rng.choices(ids, k=self.iterations + self.warmup)
        idx = 0

        def q():
            nonlocal idx
            nid = lookup_ids[idx % len(lookup_ids)]
            idx += 1
            self.execute("MATCH (n:User {user_id: $id}) RETURN n", {"id": nid})

        return self.measure("Point lookup (by user_id)", q)

    def bench_filtered_lookup(self) -> Stats:
        def q():
            self.execute(
                "MATCH (n:User) WHERE n.age > 25 AND n.gender = '1' RETURN count(n) AS cnt"
            )
        return self.measure("Filtered lookup (age > 25 AND gender=1)", q)

    def bench_aggregation(self) -> Stats:
        def q():
            self.execute(
                "MATCH (n:User)-[:FOLLOWS]->(m:User) "
                "RETURN m.gender AS gender, count(*) AS cnt "
                "ORDER BY cnt DESC LIMIT 10"
            )
        return self.measure("Aggregation (count follows by gender)", q)

    def run_all_sequential(self) -> dict[str, Stats]:
        """Run all sequential benchmarks and return a name → Stats map."""
        print(f"\n{'='*60}")
        print(f"  Benchmarking: {self.DB_NAME}")
        print(f"{'='*60}")
        results = {}
        for bench_name, bench_fn in [
            ("traversal_1hop", self.bench_1hop),
            ("traversal_2hop", self.bench_2hop),
            ("traversal_3hop", self.bench_3hop),
            ("point_lookup", self.bench_point_lookup),
            ("filtered_lookup", self.bench_filtered_lookup),
            ("aggregation", self.bench_aggregation),
        ]:
            try:
                results[bench_name] = bench_fn()
            except Exception as e:
                print(f"  [{self.DB_NAME}] FAILED {bench_name}: {e}")
                results[bench_name] = None
        return results


def save_stats_csv(all_results: dict[str, dict[str, Stats | None]], output_path: Path) -> None:
    """
    Save all Stats to a CSV file.
    all_results: { db_name -> { bench_name -> Stats } }
    """
    rows = []
    for db_name, benchmarks in all_results.items():
        for bench_name, stats in benchmarks.items():
            if stats is None:
                rows.append({
                    "db": db_name, "benchmark": bench_name,
                    "p50_ms": "ERROR", "p95_ms": "ERROR",
                    "mean_ms": "ERROR", "min_ms": "ERROR",
                    "max_ms": "ERROR", "iterations": 0,
                })
            else:
                rows.append({
                    "db": stats.db_name,
                    "benchmark": stats.name,
                    "p50_ms": round(stats.p50_ms, 3),
                    "p95_ms": round(stats.p95_ms, 3),
                    "mean_ms": round(stats.mean_ms, 3),
                    "min_ms": round(stats.min_ms, 3),
                    "max_ms": round(stats.max_ms, 3),
                    "iterations": stats.iterations,
                })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["db", "benchmark", "p50_ms", "p95_ms",
                                               "mean_ms", "min_ms", "max_ms", "iterations"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults saved → {output_path}")
