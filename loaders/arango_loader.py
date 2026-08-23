#!/usr/bin/env python3
"""
loaders/arango_loader.py — ArangoDB data loader
================================================
Uses the python-arango driver (HTTP/REST API).
Creates a 'User' vertex collection and a 'FOLLOWS' edge collection,
then batch-inserts nodes and edges.

ArangoDB graph model:
  Vertex collection : benchmark_users
  Edge collection   : benchmark_follows
  Named graph       : benchmark_graph
"""

import os
from pathlib import Path

from arango import ArangoClient
from dotenv import load_dotenv

from loaders.base_loader import BaseLoader

load_dotenv()

VERTEX_COLLECTION = "benchmark_users"
EDGE_COLLECTION = "benchmark_follows"
GRAPH_NAME = "benchmark_graph"


class ArangoLoader(BaseLoader):
    DB_NAME = "ArangoDB"

    def __init__(self, nodes_csv: Path, edges_csv: Path, batch_size: int = 500):
        super().__init__(nodes_csv, edges_csv, batch_size)
        self._client = None
        self._db = None
        self._users = None
        self._follows = None

    def connect(self) -> None:
        uri = os.environ.get("ARANGO_URI", "http://localhost:8529")
        user = os.environ.get("ARANGO_USER", "root")
        password = os.environ.get("ARANGO_PASSWORD", "benchmarkpass")
        db_name = os.environ.get("ARANGO_DB", "benchmark")

        self._client = ArangoClient(hosts=uri)
        sys_db = self._client.db("_system", username=user, password=password)

        # Create database if it doesn't exist
        if not sys_db.has_database(db_name):
            sys_db.create_database(db_name)

        self._db = self._client.db(db_name, username=user, password=password)
        print(f"  [{self.DB_NAME}] Connected to {uri}/{db_name}")

    def close(self) -> None:
        # python-arango has no explicit close
        pass

    def clear(self) -> None:
        print(f"  [{self.DB_NAME}] Clearing existing data ...")
        # Drop and recreate the named graph (drops collections too)
        if self._db.has_graph(GRAPH_NAME):
            self._db.delete_graph(GRAPH_NAME, drop_collections=True)

        # Recreate vertex collection
        self._users = self._db.create_collection(VERTEX_COLLECTION)

        # Recreate edge collection
        self._follows = self._db.create_collection(
            EDGE_COLLECTION, edge=True
        )

        # Recreate named graph
        self._db.create_graph(
            GRAPH_NAME,
            edge_definitions=[{
                "edge_collection": EDGE_COLLECTION,
                "from_vertex_collections": [VERTEX_COLLECTION],
                "to_vertex_collections": [VERTEX_COLLECTION],
            }],
        )

    def create_indexes(self) -> None:
        print(f"  [{self.DB_NAME}] Creating indexes ...")
        # user_id is already _key so it's indexed automatically
        self._users.add_persistent_index(fields=["age"])
        self._users.add_persistent_index(fields=["gender"])

    def load_nodes(self, batch: list[dict]) -> None:
        docs = []
        for row in batch:
            doc = {
                "_key": str(row["user_id"]),
                "user_id": int(row["user_id"]),
                "gender": row["gender"],
                "age": int(row["age"]) if row["age"] not in ("null", "", None) else None,
                "region": row["region"],
            }
            docs.append(doc)
        self._users.import_bulk(docs, on_duplicate="replace")

    def load_edges(self, batch: list[dict]) -> None:
        docs = []
        for row in batch:
            src_key = str(row["src_id"])
            dst_key = str(row["dst_id"])
            docs.append({
                "_from": f"{VERTEX_COLLECTION}/{src_key}",
                "_to": f"{VERTEX_COLLECTION}/{dst_key}",
            })
        self._follows.import_bulk(docs, on_duplicate="replace")
