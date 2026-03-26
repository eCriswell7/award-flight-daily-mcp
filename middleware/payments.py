"""
Stripe payment middleware for MCP server micropayments.

Handles payment sessions for agents exceeding free tier limits.
Free tier: 10 queries/day, no payment
Pro tier: $0.01 per query (paid via Stripe)
Enterprise tier: custom pricing, unlimited

Payment flow:
1. Agent makes query
2. If free tier and under limit → serve
3. If over limit → check for valid payment session
4. If no payment → return HTTP 402 with Stripe Checkout URL
5. Agent pays → gets session token
6. Agent retries with token → query served
"""

import os
import duckdb
import stripe
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from ..config import DUCKDB_PATH

# Initialize Stripe
stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "")
stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
site_url = os.getenv("SITE_URL", "https://awardflightdaily.com")

if stripe_secret_key:
    stripe.api_key = stripe_secret_key

_conn = None


def get_conn():
    """Get or initialize DuckDB connection for writing."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(DUCKDB_PATH, read_only=False)
    return _conn


def ensure_payment_tables():
    """Create payment tracking tables if they don't exist."""
    try:
        conn = get_conn()

        # Payment sessions: tracks Stripe checkout sessions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_payment_sessions (
                session_id VARCHAR PRIMARY KEY,
                stripe_session_id VARCHAR,
                agent_id VARCHAR,
                amount_cents INTEGER,
                query_count INTEGER,
                queries_remaining INTEGER,
                status VARCHAR,
                payment_timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT now(),
                expires_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Payment events: tracks Stripe webhook events and query consumption
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_payment_events (
                id INTEGER PRIMARY KEY DEFAULT nextval('seq_payment_event_id'),
                session_id VARCHAR,
                event_type VARCHAR,
                agent_id VARCHAR,
                amount_cents INTEGER,
                timestamp TIMESTAMP DEFAULT now(),
                details_json VARCHAR
            )
        """)

        # Ensure sequences exist
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_payment_event_id START 1
        """)

        conn.commit()
    except Exception:
        # Tables might already exist
        pass


def create_payment_session(agent_id: str, query_count: int = 10) -> Tuple[str, str, str]:
    """
    Create a Stripe Checkout session for payment.

    Args:
        agent_id: Unique agent identifier
        query_count: Number of queries to purchase (default: 10)

    Returns:
        tuple: (session_id, stripe_session_url, error_message)
        - session_id: Session token for agent to use after payment
        - stripe_session_url: URL for agent to visit and pay
        - error_message: Empty string if success, error text if failed

    Raises:
        ValueError: If Stripe not configured
    """
    if not stripe_secret_key:
        return "", "", "Payment processing not configured"

    try:
        ensure_payment_tables()

        # Calculate amount: $0.01 per query
        amount_cents = query_count * 1

        # Create Stripe checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            success_url=f"{site_url}/mcp/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{site_url}/mcp/payment-cancel?agent_id={agent_id}",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "Award Flight Daily MCP Query Credits",
                            "description": f"{query_count} API queries",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": query_count,
                }
            ],
            metadata={
                "agent_id": agent_id,
                "query_count": str(query_count),
            },
        )

        # Generate session token
        session_id = f"afd_pay_{secrets.token_hex(16)}"

        # Store in database
        conn = get_conn()
        expires_at = datetime.utcnow() + timedelta(hours=24)

        conn.execute(
            """
            INSERT INTO mcp_payment_sessions
            (session_id, stripe_session_id, agent_id, amount_cents, query_count,
             queries_remaining, status, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id,
                checkout_session.id,
                agent_id,
                amount_cents,
                query_count,
                query_count,
                "pending",
                expires_at.isoformat(),
            ],
        )

        conn.commit()

        return session_id, checkout_session.url, ""

    except stripe.error.StripeError as e:
        return "", "", f"Stripe error: {str(e)}"
    except Exception as e:
        return "", "", f"Payment session error: {str(e)}"


def verify_payment(session_token: str) -> Tuple[bool, str, int]:
    """
    Verify a payment session is valid and has remaining credits.

    Args:
        session_token: Payment session token from agent

    Returns:
        tuple: (is_valid, agent_id, queries_remaining)
        - is_valid: True if session is valid and has credits
        - agent_id: Agent ID if valid, empty string if invalid
        - queries_remaining: Number of queries still available

    Raises:
        ValueError: If session not found or expired
    """
    try:
        ensure_payment_tables()
        conn = get_conn()

        result = conn.execute(
            """
            SELECT agent_id, queries_remaining, status, expires_at
            FROM mcp_payment_sessions
            WHERE session_id = ?
            """,
            [session_token],
        ).fetchone()

        if not result:
            return False, "", 0

        agent_id, queries_remaining, status, expires_at = result

        # Check if expired
        if expires_at:
            expires = datetime.fromisoformat(expires_at)
            if datetime.utcnow() > expires:
                return False, "", 0

        # Only valid if paid
        if status != "paid":
            return False, "", 0

        # Must have remaining queries
        if queries_remaining <= 0:
            return False, "", 0

        return True, agent_id, queries_remaining

    except Exception as e:
        return False, "", 0


def consume_credit(session_token: str) -> Tuple[bool, str]:
    """
    Decrement remaining credits for a paid query.

    Args:
        session_token: Payment session token

    Returns:
        tuple: (success, error_message)

    Raises:
        ValueError: If session not found or out of credits
    """
    try:
        is_valid, agent_id, remaining = verify_payment(session_token)
        if not is_valid:
            return False, "Invalid or expired payment session"

        if remaining <= 0:
            return False, "No remaining credits"

        ensure_payment_tables()
        conn = get_conn()

        # Decrement and log
        new_remaining = remaining - 1
        conn.execute(
            """
            UPDATE mcp_payment_sessions
            SET queries_remaining = ?
            WHERE session_id = ?
            """,
            [new_remaining, session_token],
        )

        # Log the consumption
        conn.execute(
            """
            INSERT INTO mcp_payment_events
            (session_id, event_type, agent_id, amount_cents, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                session_token,
                "query_consumed",
                agent_id,
                1,  # $0.01 per query
                json.dumps({"queries_remaining": new_remaining}),
            ],
        )

        conn.commit()
        return True, ""

    except Exception as e:
        return False, f"Credit consumption error: {str(e)}"


def get_payment_stats(days: int = 7) -> Dict:
    """
    Get payment and revenue analytics.

    Args:
        days: Number of days to include in stats (default: 7)

    Returns:
        dict: {
            'total_revenue_cents': int,
            'total_queries_paid': int,
            'active_sessions': int,
            'completed_sessions': int,
            'revenue_by_day': {date: cents, ...},
            'top_agents': [(agent_id, revenue_cents), ...],
            'average_session_value': cents
        }
    """
    try:
        ensure_payment_tables()
        conn = get_conn()

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total revenue from completed sessions
        result = conn.execute(
            """
            SELECT SUM(amount_cents) as revenue
            FROM mcp_payment_sessions
            WHERE status = 'paid' AND completed_at >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()],
        ).fetchone()
        total_revenue = result[0] if result and result[0] else 0

        # Total queries paid (sum of query_count for paid sessions)
        result = conn.execute(
            """
            SELECT SUM(query_count) as queries
            FROM mcp_payment_sessions
            WHERE status = 'paid' AND completed_at >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()],
        ).fetchone()
        total_queries_paid = result[0] if result and result[0] else 0

        # Active sessions (pending)
        result = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM mcp_payment_sessions
            WHERE status = 'pending' AND created_at >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()],
        ).fetchone()
        active_sessions = result[0] if result else 0

        # Completed sessions
        result = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM mcp_payment_sessions
            WHERE status = 'paid' AND completed_at >= CAST(? AS TIMESTAMP)
            """,
            [cutoff_date.isoformat()],
        ).fetchone()
        completed_sessions = result[0] if result else 0

        # Revenue by day
        rows = conn.execute(
            """
            SELECT CAST(completed_at AS DATE) as day, SUM(amount_cents) as revenue
            FROM mcp_payment_sessions
            WHERE status = 'paid' AND completed_at >= CAST(? AS TIMESTAMP)
            GROUP BY CAST(completed_at AS DATE)
            ORDER BY day DESC
            """,
            [cutoff_date.isoformat()],
        ).fetchall()
        revenue_by_day = {str(row[0]): row[1] for row in rows if row[1]}

        # Top agents by revenue
        rows = conn.execute(
            """
            SELECT agent_id, SUM(amount_cents) as revenue
            FROM mcp_payment_sessions
            WHERE status = 'paid' AND completed_at >= CAST(? AS TIMESTAMP)
            GROUP BY agent_id
            ORDER BY revenue DESC
            LIMIT 10
            """,
            [cutoff_date.isoformat()],
        ).fetchall()
        top_agents = [(row[0], row[1]) for row in rows]

        # Average session value
        avg_session = 0
        if completed_sessions > 0:
            avg_session = total_revenue // completed_sessions

        return {
            "total_revenue_cents": int(total_revenue) if total_revenue else 0,
            "total_queries_paid": int(total_queries_paid) if total_queries_paid else 0,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "revenue_by_day": revenue_by_day,
            "top_agents": top_agents,
            "average_session_value": avg_session,
        }

    except Exception as e:
        return {
            "error": str(e),
            "total_revenue_cents": 0,
            "total_queries_paid": 0,
            "active_sessions": 0,
            "completed_sessions": 0,
            "revenue_by_day": {},
            "top_agents": [],
            "average_session_value": 0,
        }


def handle_webhook(payload: bytes, sig_header: str) -> Tuple[bool, str]:
    """
    Handle Stripe webhook events.

    Signature verification and event processing for:
    - checkout.session.completed: Payment successful

    Args:
        payload: Raw request body (bytes)
        sig_header: Stripe-Signature header value

    Returns:
        tuple: (success, message)

    Raises:
        ValueError: If signature verification fails
    """
    if not stripe_webhook_secret:
        return False, "Webhook secret not configured"

    try:
        # Verify signature
        event = stripe.Webhook.construct_event(payload, sig_header, stripe_webhook_secret)

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            stripe_session_id = session["id"]
            metadata = session.get("metadata", {})

            # Find matching payment session
            ensure_payment_tables()
            conn = get_conn()

            result = conn.execute(
                """
                SELECT session_id, agent_id, query_count, amount_cents
                FROM mcp_payment_sessions
                WHERE stripe_session_id = ?
                """,
                [stripe_session_id],
            ).fetchone()

            if result:
                session_id, agent_id, query_count, amount_cents = result

                # Mark as paid
                conn.execute(
                    """
                    UPDATE mcp_payment_sessions
                    SET status = 'paid', completed_at = now()
                    WHERE session_id = ?
                    """,
                    [session_id],
                )

                # Log event
                conn.execute(
                    """
                    INSERT INTO mcp_payment_events
                    (session_id, event_type, agent_id, amount_cents, details_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        session_id,
                        "payment_completed",
                        agent_id,
                        amount_cents,
                        json.dumps(
                            {
                                "stripe_session_id": stripe_session_id,
                                "query_count": query_count,
                            }
                        ),
                    ],
                )

                conn.commit()
                return True, f"Payment processed for session {session_id}"

        return True, f"Event {event['type']} received"

    except stripe.error.SignatureVerificationError:
        return False, "Invalid signature"
    except Exception as e:
        return False, f"Webhook error: {str(e)}"


def get_session_info(session_token: str) -> Optional[Dict]:
    """
    Get detailed information about a payment session.

    Args:
        session_token: Payment session token

    Returns:
        dict or None: Session info if found, None if not found

    Raises:
        Exception: On database error
    """
    try:
        ensure_payment_tables()
        conn = get_conn()

        result = conn.execute(
            """
            SELECT session_id, agent_id, amount_cents, query_count,
                   queries_remaining, status, created_at, expires_at
            FROM mcp_payment_sessions
            WHERE session_id = ?
            """,
            [session_token],
        ).fetchone()

        if not result:
            return None

        return {
            "session_id": result[0],
            "agent_id": result[1],
            "amount_cents": result[2],
            "query_count": result[3],
            "queries_remaining": result[4],
            "status": result[5],
            "created_at": str(result[6]) if result[6] else None,
            "expires_at": str(result[7]) if result[7] else None,
        }

    except Exception as e:
        return None
