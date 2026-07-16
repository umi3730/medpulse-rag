#!/usr/bin/env python3
# coding: utf-8
"""Small Neo4j official-driver wrapper with the py2neo methods this project uses."""
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase


class Neo4jResult:
    def __init__(self, records: list[dict[str, Any]]):
        self._records = records

    def data(self) -> list[dict[str, Any]]:
        return self._records

    def evaluate(self) -> Any:
        if not self._records:
            return None
        first = self._records[0]
        if not first:
            return None
        return next(iter(first.values()))


class Neo4jGraph:
    """Compatibility wrapper for the subset of py2neo.Graph used here."""

    def __init__(self, uri: str, auth: tuple[str, str], name: str | None = None):
        self.database = name
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def run(self, cypher: str, parameters: dict[str, Any] | None = None, **kwargs) -> Neo4jResult:
        params = dict(parameters or {})
        params.update(kwargs)
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, params)
            records = [record.data() for record in result]
            result.consume()
        return Neo4jResult(records)

    def evaluate(self, cypher: str, parameters: dict[str, Any] | None = None, **kwargs) -> Any:
        return self.run(cypher, parameters, **kwargs).evaluate()

    def close(self) -> None:
        self.driver.close()
