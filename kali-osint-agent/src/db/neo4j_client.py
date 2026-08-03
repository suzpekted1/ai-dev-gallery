"""Async Neo4j client for the OSINT knowledge graph."""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncManagedTransaction

from configs.settings import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Thin wrapper around the Neo4j async driver."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._driver.close()

    async def run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        *,
        write: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute an arbitrary Cypher query and return all records as dicts."""
        async with self._driver.session() as session:
            if write:
                result = await session.execute_write(
                    self._run_tx, query, parameters or {}
                )
            else:
                result = await session.execute_read(
                    self._run_tx, query, parameters or {}
                )
            return result

    @staticmethod
    async def _run_tx(
        tx: AsyncManagedTransaction,
        query: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        result = await tx.run(query, parameters)
        records = await result.data()
        return records

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def create_node(
        self,
        label: str,
        props: dict[str, Any],
    ) -> dict[str, Any]:
        """CREATE a new node with the given label and properties."""
        query = f"CREATE (n:{label} $props) RETURN n"  # noqa: S608
        rows = await self.run_query(query, {"props": props}, write=True)
        return rows[0] if rows else {}

    async def merge_node(
        self,
        label: str,
        match_keys: dict[str, Any],
        set_keys: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """MERGE a node -- create if it doesn't exist, otherwise update.

        ``match_keys`` are used in the MERGE clause; ``set_keys`` are applied
        with ``ON CREATE SET`` and ``ON MATCH SET``.
        """
        match_clause = ", ".join(f"{k}: $match.{k}" for k in match_keys)
        query = f"MERGE (n:{label} {{{match_clause}}})"  # noqa: S608

        if set_keys:
            set_parts = ", ".join(f"n.{k} = $set.{k}" for k in set_keys)
            query += f" ON CREATE SET {set_parts} ON MATCH SET {set_parts}"

        query += " RETURN n"
        params: dict[str, Any] = {"match": match_keys}
        if set_keys:
            params["set"] = set_keys
        rows = await self.run_query(query, params, write=True)
        return rows[0] if rows else {}

    async def create_relationship(
        self,
        from_label: str,
        from_match: dict[str, Any],
        to_label: str,
        to_match: dict[str, Any],
        rel_type: str,
        rel_props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """MERGE a relationship between two matched nodes."""
        from_clause = ", ".join(f"{k}: $from.{k}" for k in from_match)
        to_clause = ", ".join(f"{k}: $to.{k}" for k in to_match)

        query = (
            f"MATCH (a:{from_label} {{{from_clause}}}), "
            f"(b:{to_label} {{{to_clause}}}) "
            f"MERGE (a)-[r:{rel_type}]->(b)"
        )

        if rel_props:
            set_parts = ", ".join(f"r.{k} = $rel.{k}" for k in rel_props)
            query += f" SET {set_parts}"

        query += " RETURN type(r) AS rel_type"

        params: dict[str, Any] = {"from": from_match, "to": to_match}
        if rel_props:
            params["rel"] = rel_props

        rows = await self.run_query(query, params, write=True)
        return rows[0] if rows else {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def find_by_label(
        self,
        label: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Find nodes by label with optional property filters."""
        where_clause = ""
        params: dict[str, Any] = {"limit": limit}

        if filters:
            conditions = []
            for i, (key, value) in enumerate(filters.items()):
                param_name = f"f{i}"
                conditions.append(f"n.{key} = ${param_name}")
                params[param_name] = value
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"MATCH (n:{label}) {where_clause} RETURN n LIMIT $limit"  # noqa: S608
        return await self.run_query(query, params)

    async def get_target_graph(
        self,
        target: str,
        max_hops: int = 3,
    ) -> list[dict[str, Any]]:
        """Return the subgraph reachable from a Target node within *max_hops*.

        Returns nodes and relationships up to 3 hops from the target.
        """
        query = (
            "MATCH path = (t:Target {domain: $target})-[*1.." + str(max_hops) + "]-(connected) "
            "RETURN t AS source, "
            "[n IN nodes(path) | {labels: labels(n), props: properties(n)}] AS nodes, "
            "[r IN relationships(path) | {type: type(r), props: properties(r), "
            "start: id(startNode(r)), end: id(endNode(r))}] AS relationships"
        )
        return await self.run_query(query, {"target": target})

    # ------------------------------------------------------------------
    # Schema / constraints
    # ------------------------------------------------------------------

    async def init_constraints(self) -> None:
        """Create uniqueness constraints for core node types."""
        constraints = [
            ("Target", "domain"),
            ("Email", "address"),
            ("Subdomain", "name"),
        ]
        for label, prop in constraints:
            query = (
                f"CREATE CONSTRAINT IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
            await self.run_query(query, write=True)

        # Camera has a composite key: (ip, port)
        camera_query = (
            "CREATE CONSTRAINT IF NOT EXISTS "
            "FOR (n:Camera) REQUIRE (n.ip, n.port) IS UNIQUE"
        )
        await self.run_query(camera_query, write=True)

        logger.info("Neo4j constraints initialized")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

neo4j_client = Neo4jClient(
    uri=settings.neo4j_uri,
    user=settings.neo4j_user,
    password=settings.neo4j_password,
)
