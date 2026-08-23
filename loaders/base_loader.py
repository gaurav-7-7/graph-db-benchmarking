#!/usr/bin/env python3
"""
loaders/base_loader.py — Abstract base class for all database loaders
"""

import csv
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoadResult:
    """Statistics from a data load operation."""
    db_name: str
    node_count: int
    edge_count: int
    total_seconds: float
    nodes_per_second: float
    edges_per_second: float

    def __str__(self) -> str:
        return (
            f"[{self.db_name}] Load complete: "
            f"{self.node_count:,} nodes ({self.nodes_per_second:.0f}/s), "
            f"{self.edge_count:,} edges ({self.edges_per_second:.0f}/s) "
            f"in {self.total_seconds:.1f}s"
        )


class BaseLoader(ABC):
    """
    Abstract loader. Subclasses implement connect(), clear(), load_nodes(),
    and load_edges(). The run() method times the full load and returns a
    LoadResult.
    """

    DB_NAME: str = "unknown"

    def __init__(self, nodes_csv: Path, edges_csv: Path, batch_size: int = 500):
        self.nodes_csv = nodes_csv
        self.edges_csv = edges_csv
        self.batch_size = batch_size

    # ── To implement ──────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""

    @abstractmethod
    def clear(self) -> None:
        """Drop all data so the load is idempotent."""

    @abstractmethod
    def create_indexes(self) -> None:
        """Create indexes needed for lookup benchmarks."""

    @abstractmethod
    def load_nodes(self, batch: list[dict]) -> None:
        """Insert a batch of node dicts (keys: user_id, gender, age, region)."""

    @abstractmethod
    def load_edges(self, batch: list[dict]) -> None:
        """Insert a batch of edge dicts (keys: src_id, dst_id)."""

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def read_nodes_csv(path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def read_edges_csv(path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _chunks(lst: list, size: int):
        for i in range(0, len(lst), size):
            yield lst[i : i + size]

    # ── Orchestrated run ──────────────────────────────────────────────────────

    def run(self) -> LoadResult:
        """Connect, clear, load all nodes + edges, return timing stats."""
        self.connect()
        self.clear()
        self.create_indexes()

        nodes = self.read_nodes_csv(self.nodes_csv)
        edges = self.read_edges_csv(self.edges_csv)

        # ── Load nodes ────────────────────────────────────────────────────
        t0 = time.perf_counter()
        for batch in self._chunks(nodes, self.batch_size):
            self.load_nodes(batch)
        node_time = time.perf_counter() - t0

        # ── Load edges ────────────────────────────────────────────────────
        t1 = time.perf_counter()
        for batch in self._chunks(edges, self.batch_size):
            self.load_edges(batch)
        edge_time = time.perf_counter() - t1

        total = node_time + edge_time
        result = LoadResult(
            db_name=self.DB_NAME,
            node_count=len(nodes),
            edge_count=len(edges),
            total_seconds=total,
            nodes_per_second=len(nodes) / node_time if node_time > 0 else 0,
            edges_per_second=len(edges) / edge_time if edge_time > 0 else 0,
        )
        print(result)
        self.close()
        return result
