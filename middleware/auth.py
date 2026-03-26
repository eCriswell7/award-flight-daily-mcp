"""
API key management and validation for MCP server.
Supports free, pro, and enterprise tiers.
"""

import os
import duckdb
import secrets
from datetime import datetime
from ..config import DUCKDB_PATH


_conn = None
_master_key = os.getenv("MCP_MASTER_KEY", "")


def get_conn():
    """Get or initialize DuckDB connection for writing."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(DUCKDB_PATH, read_only=False)
    return _conn


def ensure_keys_table():
    """Create mcp_api_keys table if it doesn't exist."""
    try:
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_api_keys (
                api_key VARCHAR PRIMARY KEY,
                agent_id VARCHAR,
                tier VARCHAR,
                created_at TIMESTAMP DEFAULT now(),
                active BOOLEAN DEFAULT true,
                created_by VARCHAR,
                last_used_at TIMESTAMP
            )
        """)
        conn.commit()
    except Exception:
        # Table might already exist
        pass


def generate_api_key(agent_id=None, tier="free"):
    """
    Generate a new MCP API key.

    Args:
        agent_id: Optional agent identifier (auto-generated if not provided)
        tier: free, pro, or enterprise (default: free)

    Returns:
        str: API key in format afd_<32 hex chars>
    """
    if tier not in ["free", "pro", "enterprise"]:
        tier = "free"

    try:
        ensure_keys_table()
        conn = get_conn()

        # Generate key
        key = f"afd_{secrets.token_hex(16)}"

        # Auto-generate agent_id if not provided
        if not agent_id:
            agent_id = f"agent_{secrets.token_hex(4)}"

        # Insert into DB
        conn.execute(
            """
            INSERT INTO mcp_api_keys
            (api_key, agent_id, tier, active, created_by)
            VALUES (?, ?, ?, true, 'admin')
            """,
            [key, agent_id, tier]
        )
        conn.commit()
        return key
    except Exception as e:
        raise Exception(f"Failed to generate API key: {str(e)}")


def validate_api_key(key):
    """
    Validate an API key and return tier if valid.
    Also checks master key.

    Args:
        key: API key to validate

    Returns:
        dict: {
            'valid': bool,
            'tier': str or None,
            'agent_id': str or None,
            'error': str or None
        }
    """
    if not key:
        return {"valid": False, "tier": None, "agent_id": None, "error": "Missing API key"}

    # Check master key first
    if _master_key and key == _master_key:
        return {"valid": True, "tier": "enterprise", "agent_id": "admin", "error": None}

    try:
        ensure_keys_table()
        conn = get_conn()

        result = conn.execute(
            """
            SELECT tier, agent_id, active FROM mcp_api_keys

            WHERE api_key = ?
            """,
            [key]
        ).fetchone()

        if not result:
            return {"valid": False, "tier": None, "agent_id": None, "error": "Invalid API key"}

        tier, agent_id, active = result

        if not active:
            return {"valid": False, "tier": None, "agent_id": None, "error": "API key is inactive"}

        # Update last_used_at
        try:
            conn.execute(
                "UPDATE mcp_api_keys SET last_used_at = now() WHERE api_key = ?",
                [key]
            )
            conn.commit()
        except:
            pass

        return {"valid": True, "tier": tier, "agent_id": agent_id, "error": None}
    except Exception as e:
        return {"valid": False, "tier": None, "agent_id": None, "error": f"Validation error: {str(e)}"}


def check_rate_limit(agent_id, tier):
    """
    Check if agent is within rate limits for their tier.
    Uses in-memory tracking (from rate_limiter module).

    This is a wrapper that delegates to rate_limiter.py
    Returns dict with allowed, remaining, reset_at.
    """
    try:
        from .rate_limiter import check_rate_limit as _check_rate_limit
        return _check_rate_limit(agent_id, tier)
    except ImportError:
        # Fallback: return unlimited
        return {
            "allowed": True,
            "remaining": 999999,
            "reset_at": None
        }


def get_key_info(key):
    """
    Get detailed info about an API key.

    Returns:
        dict with key, agent_id, tier, created_at, active, last_used_at
    """
    try:
        ensure_keys_table()
        conn = get_conn()

        result = conn.execute(
            """
            SELECT api_key, agent_id, tier, created_at, active, last_used_at
            FROM mcp_api_keys
            WHERE api_key = ?
            """,
            [key]
        ).fetchone()

        if not result:
            return None

        return {
            "api_key": result[0],
            "agent_id": result[1],
            "tier": result[2],
            "created_at": str(result[3]) if result[3] else None,
            "active": result[4],
            "last_used_at": str(result[5]) if result[5] else None
        }
    except Exception as e:
        return None


def revoke_api_key(key):
    """
    Deactivate an API key.

    Returns:
        bool: True if revoked successfully
    """
    try:
        ensure_keys_table()
        conn = get_conn()

        conn.execute(
            "UPDATE mcp_api_keys SET active = false WHERE api_key = ?",
            [key]
        )
        conn.commit()
        return True
    except Exception:
        return False
