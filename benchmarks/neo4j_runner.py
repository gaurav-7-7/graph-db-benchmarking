#!/usr/bin/env python3
"""
benchmarks/neo4j_runner.py
==========================
Shared runner for CognoDB / Neo4j AuraDB / Memgraph / FalkorDB.
All use the official neo4j Python driver over Bolt.
"""

import os
import random

from dotenv import load_dotenv
from neo4j import GraphDatabase

from benchmarks.base_runner import BaseRunner

load_dotenv()


class Neo4jRunner(BaseRunner):
    """Bolt/Cypher runner — works for CognoDB, AuraDB, Memgraph, FalkorDB."""

    def __init__(self, db_name: str, uri: str, user: str, password: str, **kwargs):
        super().__init__(**kwargs)
        self.DB_NAME = db_name
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    # ── Factory class methods ─────────────────────────────────────────────────

    @classmethod
    def for_cognodb(cls, **kwargs):
        return cls(
            db_name="CognoDB",
            uri=os.environ["COGNODB_URI"],
            user=os.environ["COGNODB_USER"],
            password=os.environ["COGNODB_PASSWORD"],
            **kwargs,
        )

    @classmethod
    def for_auradb(cls, **kwargs):
        return cls(
            db_name="Neo4j AuraDB",
            uri=os.environ["NEO4J_URI"],
            user=os.environ["NEO4J_USER"],
            password=os.environ["NEO4J_PASSWORD"],
            **kwargs,
        )

    @classmethod
    def for_memgraph(cls, **kwargs):
        return cls(
            db_name="Memgraph",
            uri=os.environ["MEMGRAPH_URI"],
            user=os.environ["MEMGRAPH_USER"],
            password=os.environ["MEMGRAPH_PASSWORD"],
            **kwargs,
        )

    @classmethod
    def for_falkordb(cls, **kwargs):
        return cls(
            db_name="FalkorDB",
            uri=os.environ.get("FALKORDB_URI", "bolt://localhost:7688"),
            user=os.environ.get("FALKORDB_USER", ""),
            password=os.environ.get("FALKORDB_PASSWORD", ""),
            **kwargs,
        )

    # ── BaseRunner implementation ─────────────────────────────────────────────

    def connect(self) -> None:
        auth = (self._user, self._password) if self._user else None
        self._driver = GraphDatabase.driver(self._uri, auth=auth)
        self._driver.verify_connectivity()
        print(f"  [{self.DB_NAME}] Connected")

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def execute(self, query: str, params: dict | None = None) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(r) for r in result]

    def fetch_sample_node_ids(self, n: int, seed: int) -> list[int]:
        """
        Fetch n random user_id values from the DB.
        Uses ORDER BY rand() which is supported by Neo4j/Memgraph/FalkorDB.
        """
        result = self.execute(
            f"MATCH (u:User) RETURN u.user_id AS user_id LIMIT {n * 10}"
        )
        ids = [r["user_id"] for r in result if r["user_id"] is not None]
        rng = random.Random(seed)
        return rng.sample(ids, min(n, len(ids)))
