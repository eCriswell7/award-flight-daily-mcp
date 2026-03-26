"""
Usage logging and analytics for MCP API calls.
Tracks per-agent usage, response times, errors, and revenue.
"""

import duckdb
import json
from datetime import datetime, timedelta
from ..config import DUCKDB_PATH


_conn = None


def get_conn():
    """Get or initialize DuckDB connection for writing."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(DUCKDB_PATH, read_only=False)
    return _conn


def ensure_usage_table():
    """Create mcp_usage_log table if it doesn't exist."""
    try:
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_usage_log (
                id INTEGER PRIMARY KEY DEFAULT nextval('seq_usage_id'),
                timestamp TIMESTAMP DEFAULT now(),
                agent_id VARCHAR,
                tool_name VARCHAR,
                params_json VARCHAR,
                response_time_ms INTEGER,
                tier VARCHAR,
                payment_cents INTEGER,
                error VARCHAR
            )
        """)
        # Ensure sequence exists
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_usage_id START 1
        """)
        conn.commit()
    except Exception as e:
        # Table might already exist
        pass


def log_usage(agent_id, tool_name, params, response_time_ms, tier, payment_info=None):
    """
    Log a single MCP API call.

    Args:
        agent_id: Unique agent identifier
        tool_name: Name of the tool called
        params: Dict of parameters (will be JSON-serialized)
        response_time_ms: Time in milliseconds
        tier: free, pro, or enterprise
        payment_info: Optional dict with payment_cents, customer_id, etc

    Returns:
        bool: True if logged successfully
    """
    try:
        ensure_usage_table()
        conn = get_conn()

        params_json = json.dumps(params) if params else None
        payment_cents = 0
        if payment_info and isinstance(payment_info, dict):
            payment_cents = payment_info.get("payment_cents", 0)

        conn.execute(
            """
            INSERT INTO mcp_usage_log
            (agent_id, tool_name, params_json, response_time_ms, tier, payment_cents, error)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            [agent_id, tool_name, params_json, response_time_ms, tier, payment_cents]
        )
        conn.commit()
        return True
    except Exception as e:
        # Log error but don't fail the request
        try:
            conn = get_conn()
            error_msg = str(e)[:255]
            conn.execute(
                """
                INSERT INTO mcp_usage_log
                (agent_id, tool_name, params_json, response_time_ms, tier, payment_cents, error)
                VALUES (?, ?, NULL, ?, ?, 0, ?)
                """,
                [agent_id, tool_name, response_time_ms, tier, error_msg]
            )
            conn.commit()
        except:
            pass
        return False


def get_usage_stats(days=7):
    """
    Get aggregated usage statistics for the past N days.

    Returns:
        dict: {
            'total_queries': int,
            'unique_agents': int,
            'revenue_cents': int,
            'queries_by_tool': {tool: count, ...},
            'queries_by_day': {date: count, ...},
            'top_agents': [(agent_id, count), ...],
            'top_routes': [(tool, count), ...],
            'error_rate': float,
            'tier_breakdown': {tier: count, ...}
        }
    """
    try:
        ensure_usage_table()
        conn = get_conn()

        # Validate days parameter
        days = max(1, min(days, 365))
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total queries in period
        result = conn.execute(
            """
            SELECT COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()]
        ).fetchone()
        total_queries = result[0] if result else 0

        # Unique agents
        result = conn.execute(
            """
            SELECT COUNT(DISTINCT agent_id) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()]
        ).fetchone()
        unique_agents = result[0] if result else 0

        # Revenue
        result = conn.execute(
            """
            SELECT SUM(COALESCE(payment_cents, 0)) as revenue FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()]
        ).fetchone()
        revenue_cents = result[0] if result and result[0] else 0

        # Queries by tool
        rows = conn.execute(
            """
            SELECT tool_name, COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP) AND error IS NULL
            GROUP BY tool_name
            ORDER BY count DESC
            """,
            [cutoff_date.isoformat()]
        ).fetchall()
        queries_by_tool = {row[0]: row[1] for row in rows}

        # Queries by day
        rows = conn.execute(
            """
            SELECT CAST(timestamp AS DATE) as day, COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            GROUP BY CAST(timestamp AS DATE)
            ORDER BY day DESC
            """,
            [cutoff_date.isoformat()]
        ).fetchall()
        queries_by_day = {str(row[0]): row[1] for row in rows}

        # Top agents
        rows = conn.execute(
            """
            SELECT agent_id, COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP) AND error IS NULL
            GROUP BY agent_id
            ORDER BY count DESC
            LIMIT 10
            """,
            [cutoff_date.isoformat()]
        ).fetchall()
        top_agents = [(row[0], row[1]) for row in rows]

        # Top routes (tools)
        rows = conn.execute(
            """
            SELECT tool_name, COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP) AND error IS NULL
            GROUP BY tool_name
            ORDER BY count DESC
            LIMIT 10
            """,
            [cutoff_date.isoformat()]
        ).fetchall()
        top_routes = [(row[0], row[1]) for row in rows]

        # Error rate
        result = conn.execute(
            """
            SELECT COUNT(*) as total, SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()]
        ).fetchone()
        error_count = result[1] if result and result[1] else 0
        error_rate = (error_count / total_queries * 100) if total_queries > 0 else 0.0

        # Tier breakdown
        rows = conn.execute(
            """
            SELECT tier, COUNT(*) as count FROM mcp_usage_log
            WHERE timestamp >= CAST(? AS TIMESTAMP)
            GROUP BY tier
            ORDER BY count DESC
            """,
            [cutoff_date.isoformat()]
        ).fetchall()
        tier_breakdown = {row[0]: row[1] for row in rows}

        return {
            "total_queries": total_queries,
            "unique_agents": unique_agents,
            "revenue_cents": int(revenue_cents),
            "queries_by_tool": queries_by_tool,
            "queries_by_day": queries_by_day,
            "top_agents": top_agents,
            "top_routes": top_routes,
            "error_rate": round(error_rate, 2),
            "tier_breakdown": tier_breakdown
        }
    except Exception as e:
        return {
            "error": str(e),
            "total_queries": 0,
            "unique_agents": 0,
            "revenue_cents": 0,
            "queries_by_tool": {},
            "queries_by_day": {},
            "top_agents": [],
            "top_routes": [],
            "error_rate": 0.0,
            "tier_breakdown": {}
        }
