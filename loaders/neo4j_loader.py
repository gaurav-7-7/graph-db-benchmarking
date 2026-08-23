#!/usr/bin/env python3
"""
loaders/neo4j_loader.py
=======================
Shared loader for all Cypher/Bolt-speaking databases:
  - CognoDB Cloud
  - Neo4j AuraDB
  - Memgraph Cloud
  - FalkorDB (local Docker)

All four use the official `neo4j` Python driver and speak Bolt + Cypher.
The only difference between them is the connection URI and credentials,
which are injected at instantiation time from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from loaders.base_loader import BaseLoader

load_dotenv()

# ── Cypher templates ──────────────────────────────────────────────────────────

# UNWIND lets us insert an entire batch in one round-trip
_LOAD_NODES_CYPHER = """
UNWIND $batch AS row
MERGE (u:User {user_id: toInteger(row.user_id)})
SET u.gender   = row.gender,
    u.age      = CASE row.age WHEN 'null' THEN null ELSE toInteger(row.age) END,
    u.region   = row.region
"""

_LOAD_EDGES_CYPHER = """
UNWIND $batch AS row
MATCH (src:User {user_id: toInteger(row.src_id)})
MATCH (dst:User {user_id: toInteger(row.dst_id)})
MERGE (src)-[:FOLLOWS]->(dst)
"""

_CLEAR_CYPHER = "MATCH (n) DETACH DELETE n"

_INDEX_CYPHER_LIST = [
    "CREATE INDEX user_id_idx IF NOT EXISTS FOR (u:User) ON (u.user_id)",
    "CREATE INDEX user_age_idx IF NOT EXISTS FOR (u:User) ON (u.age)",
    "CREATE INDEX user_gender_idx IF NOT EXISTS FOR (u:User) ON (u.gender)",
]


class Neo4jLoader(BaseLoader):
    """
    Works for CognoDB / Neo4j AuraDB / Memgraph / FalkorDB.
    Pass uri, user, password explicitly or use the class methods:
      Neo4jLoader.for_cognodb(...)
      Neo4jLoader.for_auradb(...)
      etc.
    """

    def __init__(
        self,
        db_name: str,
        uri: str,
        user: str,
        password: str,
        nodes_csv: Path,
        edges_csv: Path,
        batch_size: int = 500,
    ):
        super().__init__(nodes_csv, edges_csv, batch_size)
        self.DB_NAME = db_name
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None
        self._session = None

    # ── Factory class methods ─────────────────────────────────────────────────

    @classmethod
    def for_cognodb(cls, nodes_csv: Path, edges_csv: Path, **kwargs):
        return cls(
            db_name="CognoDB",
            uri=os.environ["COGNODB_URI"],
            user=os.environ["COGNODB_USER"],
            password=os.environ["COGNODB_PASSWORD"],
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            **kwargs,
        )

    @classmethod
    def for_auradb(cls, nodes_csv: Path, edges_csv: Path, **kwargs):
        return cls(
            db_name="Neo4j AuraDB",
            uri=os.environ["NEO4J_URI"],
            user=os.environ["NEO4J_USER"],
            password=os.environ["NEO4J_PASSWORD"],
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            **kwargs,
        )

    @classmethod
    def for_memgraph(cls, nodes_csv: Path, edges_csv: Path, **kwargs):
        return cls(
            db_name="Memgraph",
            uri=os.environ["MEMGRAPH_URI"],
            user=os.environ["MEMGRAPH_USER"],
            password=os.environ["MEMGRAPH_PASSWORD"],
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            **kwargs,
        )

    @classmethod
    def for_falkordb(cls, nodes_csv: Path, edges_csv: Path, **kwargs):
        return cls(
            db_name="FalkorDB",
            uri=os.environ.get("FALKORDB_URI", "bolt://localhost:7688"),
            user=os.environ.get("FALKORDB_USER", ""),
            password=os.environ.get("FALKORDB_PASSWORD", ""),
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            **kwargs,
        )

    # ── BaseLoader implementation ─────────────────────────────────────────────

    def connect(self) -> None:
        auth = (self._user, self._password) if self._user else None
        self._driver = GraphDatabase.driver(self._uri, auth=auth)
        self._driver.verify_connectivity()
        print(f"  [{self.DB_NAME}] Connected to {self._uri}")

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def clear(self) -> None:
        print(f"  [{self.DB_NAME}] Clearing existing data ...")
        with self._driver.session() as session:
            session.run(_CLEAR_CYPHER)

    def create_indexes(self) -> None:
        print(f"  [{self.DB_NAME}] Creating indexes ...")
        with self._driver.session() as session:
            for cypher in _INDEX_CYPHER_LIST:
                try:
                    session.run(cypher)
                except Exception as e:
                    # FalkorDB / Memgraph may use slightly different index syntax
                    print(f"  [{self.DB_NAME}] Index warning: {e}")

    def load_nodes(self, batch: list[dict]) -> None:
        with self._driver.session() as session:
            session.run(_LOAD_NODES_CYPHER, batch=batch)

    def load_edges(self, batch: list[dict]) -> None:
        with self._driver.session() as session:
            session.run(_LOAD_EDGES_CYPHER, batch=batch)
