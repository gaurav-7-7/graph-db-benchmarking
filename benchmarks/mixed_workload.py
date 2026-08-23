#!/usr/bin/env python3
"""
benchmarks/mixed_workload.py — Concurrent read/write throughput benchmark
==========================================================================
Runs a sustained mixed workload (70% reads / 30% writes) at configurable
concurrency levels (1, 10, 40 clients) for a fixed duration.

Returns: queries-per-second at each concurrency level.
"""

import random
import threading
import time
from dataclasses import dataclass

from benchmarks.base_runner import BaseRunner


@dataclass
class MixedWorkloadResult:
    db_name: str
    concurrency: int
    duration_seconds: int
    total_queries: int
    read_queries: int
    write_queries: int
    qps: float
    read_qps: float
    write_qps: float
    errors: int

    def summary_line(self) -> str:
        return (
            f"  [{self.db_name}] Mixed workload @ {self.concurrency} clients: "
            f"{self.qps:.1f} QPS  (reads={self.read_qps:.1f}/s, writes={self.write_qps:.1f}/s, "
            f"errors={self.errors})"
        )


def run_mixed_workload(
    runner: BaseRunner,
    concurrency_levels: list[int] = (1, 10, 40),
    duration_seconds: int = 30,
    read_ratio: float = 0.70,
    seed: int = 42,
) -> list[MixedWorkloadResult]:
    """
    Runs mixed read/write workload at each concurrency level.
    Reads  : 2-hop traversal from a random sample node
    Writes : INSERT a new FOLLOWS relationship between two random sample nodes
             (then immediately DELETE it to keep data stable)
    """
    sample_ids = runner._get_sample_ids()
    results = []

    for concurrency in concurrency_levels:
        print(f"\n  [{runner.DB_NAME}] Mixed workload: {concurrency} concurrent clients × {duration_seconds}s ...")

        counters = {"reads": 0, "writes": 0, "errors": 0}
        stop_event = threading.Event()
        rng = random.Random(seed + concurrency)

        def worker():
            local_rng = random.Random(rng.random())
            while not stop_event.is_set():
                try:
                    if local_rng.random() < read_ratio:
                        # Read: 2-hop traversal
                        nid = local_rng.choice(sample_ids)
                        runner.execute(
                            "MATCH (n:User {user_id: $id})-[:FOLLOWS*2]->(m) "
                            "RETURN count(m) AS cnt",
                            {"id": nid},
                        )
                        counters["reads"] += 1
                    else:
                        # Write: create + delete a relationship (keeps data stable)
                        src, dst = local_rng.sample(sample_ids, 2)
                        runner.execute(
                            "MATCH (a:User {user_id: $src}), (b:User {user_id: $dst}) "
                            "CREATE (a)-[r:TEMP_FOLLOWS]->(b) "
                            "DELETE r",
                            {"src": src, "dst": dst},
                        )
                        counters["writes"] += 1
                except Exception:
                    counters["errors"] += 1

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()

        time.sleep(duration_seconds)
        stop_event.set()
        for t in threads:
            t.join(timeout=5)

        elapsed = time.perf_counter() - t0
        total = counters["reads"] + counters["writes"]

        r = MixedWorkloadResult(
            db_name=runner.DB_NAME,
            concurrency=concurrency,
            duration_seconds=duration_seconds,
            total_queries=total,
            read_queries=counters["reads"],
            write_queries=counters["writes"],
            qps=total / elapsed,
            read_qps=counters["reads"] / elapsed,
            write_qps=counters["writes"] / elapsed,
            errors=counters["errors"],
        )
        print(r.summary_line())
        results.append(r)

    return results


def arango_mixed_workload(
    runner,  # ArangoRunner
    concurrency_levels: list[int] = (1, 10, 40),
    duration_seconds: int = 30,
    read_ratio: float = 0.70,
    seed: int = 42,
) -> list[MixedWorkloadResult]:
    """AQL-based mixed workload for ArangoDB."""
    from benchmarks.arango_runner import VERTEX_COLLECTION, GRAPH_NAME

    sample_ids = runner._get_sample_ids()
    results = []

    for concurrency in concurrency_levels:
        print(f"\n  [{runner.DB_NAME}] Mixed workload: {concurrency} concurrent clients × {duration_seconds}s ...")
        counters = {"reads": 0, "writes": 0, "errors": 0}
        stop_event = threading.Event()
        rng = random.Random(seed + concurrency)

        def worker():
            local_rng = random.Random(rng.random())
            while not stop_event.is_set():
                try:
                    if local_rng.random() < read_ratio:
                        nid = local_rng.choice(sample_ids)
                        runner.execute(
                            f"""
                            FOR v IN 2..2 OUTBOUND
                                '{VERTEX_COLLECTION}/{nid}'
                                GRAPH '{GRAPH_NAME}'
                            COLLECT WITH COUNT INTO cnt
                            RETURN cnt
                            """
                        )
                        counters["reads"] += 1
                    else:
                        # ArangoDB write: insert + immediately remove
                        src, dst = local_rng.sample(sample_ids, 2)
                        runner.execute(
                            f"""
                            INSERT {{
                                _from: '{VERTEX_COLLECTION}/@src',
                                _to: '{VERTEX_COLLECTION}/@dst',
                                _temp: true
                            }} INTO benchmark_follows
                            """,
                            {"src": str(src), "dst": str(dst)},
                        )
                        counters["writes"] += 1
                except Exception:
                    counters["errors"] += 1

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        time.sleep(duration_seconds)
        stop_event.set()
        for t in threads:
            t.join(timeout=5)

        elapsed = time.perf_counter() - t0
        total = counters["reads"] + counters["writes"]

        r = MixedWorkloadResult(
            db_name=runner.DB_NAME,
            concurrency=concurrency,
            duration_seconds=duration_seconds,
            total_queries=total,
            read_queries=counters["reads"],
            write_queries=counters["writes"],
            qps=total / elapsed,
            read_qps=counters["reads"] / elapsed,
            write_qps=counters["writes"] / elapsed,
            errors=counters["errors"],
        )
        print(r.summary_line())
        results.append(r)

    return results
