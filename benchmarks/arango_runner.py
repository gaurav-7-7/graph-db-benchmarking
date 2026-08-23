#!/usr/bin/env python3
"""
benchmarks/arango_runner.py
===========================
ArangoDB benchmark runner using AQL (ArangoDB Query Language).
Implements semantically equivalent queries to the Cypher benchmarks.
"""

import os
import random

from arango import ArangoClient
from dotenv import load_dotenv

from benchmarks.base_runner import BaseRunner, Stats, compute_stats

load_dotenv()

VERTEX_COLLECTION = "benchmark_users"
EDGE_COLLECTION = "benchmark_follows"
GRAPH_NAME = "benchmark_graph"


class ArangoRunner(BaseRunner):
    DB_NAME = "ArangoDB"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None
        self._db = None

    def connect(self) -> None:
        uri = os.environ.get("ARANGO_URI", "http://localhost:8529")
        user = os.environ.get("ARANGO_USER", "root")
        password = os.environ.get("ARANGO_PASSWORD", "benchmarkpass")
        db_name = os.environ.get("ARANGO_DB", "benchmark")
        self._client = ArangoClient(hosts=uri)
        self._db = self._client.db(db_name, username=user, password=password)
        print(f"  [{self.DB_NAME}] Connected to {uri}/{db_name}")

    def close(self) -> None:
        pass

    def execute(self, query: str, params: dict | None = None) -> list[dict]:
        cursor = self._db.aql.execute(query, bind_vars=params or {})
        return list(cursor)

    def fetch_sample_node_ids(self, n: int, seed: int) -> list[int]:
        result = self.execute(
            f"FOR u IN {VERTEX_COLLECTION} LIMIT {n * 10} RETURN u.user_id"
        )
        ids = [r for r in result if r is not None]
        rng = random.Random(seed)
        return rng.sample(ids, min(n, len(ids)))

    # ── AQL overrides for traversal queries ───────────────────────────────────
    # ArangoDB uses its own graph traversal syntax (FOR v IN 1..N GRAPH ...)
    # These override the Cypher versions in BaseRunner

    def bench_1hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    f"""
                    FOR v IN 1..1 OUTBOUND
                        '{VERTEX_COLLECTION}/{nid}'
                        GRAPH '{GRAPH_NAME}'
                    COLLECT WITH COUNT INTO cnt
                    RETURN cnt
                    """
                )
            s = self.measure(f"1-hop traversal (node {node_id})", q,
                             iterations=max(self.iterations // len(ids), 1), warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 1-hop", self.DB_NAME, latencies)

    def bench_2hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    f"""
                    FOR v IN 2..2 OUTBOUND
                        '{VERTEX_COLLECTION}/{nid}'
                        GRAPH '{GRAPH_NAME}'
                    COLLECT WITH COUNT INTO cnt
                    RETURN cnt
                    """
                )
            s = self.measure(f"2-hop traversal (node {node_id})", q,
                             iterations=max(self.iterations // len(ids), 1), warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 2-hop", self.DB_NAME, latencies)

    def bench_3hop(self) -> Stats:
        ids = self._get_sample_ids()
        latencies = []
        for node_id in ids:
            def q(nid=node_id):
                self.execute(
                    f"""
                    FOR v IN 3..3 OUTBOUND
                        '{VERTEX_COLLECTION}/{nid}'
                        GRAPH '{GRAPH_NAME}'
                    COLLECT WITH COUNT INTO cnt
                    RETURN cnt
                    """
                )
            s = self.measure(f"3-hop traversal (node {node_id})", q,
                             iterations=max(self.iterations // len(ids), 1), warmup=2)
            latencies.extend(s.raw_ms)
        return compute_stats("Traversal 3-hop", self.DB_NAME, latencies)

    def bench_point_lookup(self) -> Stats:
        ids = self._get_sample_ids()
        rng = random.Random(self.random_seed)
        lookup_ids = rng.choices(ids, k=self.iterations + self.warmup)
        idx = 0

        def q():
            nonlocal idx
            nid = lookup_ids[idx % len(lookup_ids)]
            idx += 1
            self.execute(
                f"FOR u IN {VERTEX_COLLECTION} FILTER u.user_id == @id RETURN u",
                {"id": nid},
            )

        return self.measure("Point lookup (by user_id)", q)

    def bench_filtered_lookup(self) -> Stats:
        def q():
            self.execute(
                f"FOR u IN {VERTEX_COLLECTION} FILTER u.age > 25 AND u.gender == '1' "
                f"COLLECT WITH COUNT INTO cnt RETURN cnt"
            )
        return self.measure("Filtered lookup (age > 25 AND gender=1)", q)

    def bench_aggregation(self) -> Stats:
        def q():
            self.execute(
                f"""
                FOR e IN {EDGE_COLLECTION}
                    FOR v IN {VERTEX_COLLECTION}
                        FILTER v._id == e._to
                        COLLECT gender = v.gender WITH COUNT INTO cnt
                        SORT cnt DESC
                        LIMIT 10
                        RETURN {{ gender, cnt }}
                """
            )
        return self.measure("Aggregation (count follows by gender)", q)
