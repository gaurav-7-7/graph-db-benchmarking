#!/usr/bin/env python3
"""
loaders/__init__.py
"""
from loaders.neo4j_loader import Neo4jLoader
from loaders.arango_loader import ArangoLoader

__all__ = ["Neo4jLoader", "ArangoLoader"]
