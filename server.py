#!/usr/bin/env python3
"""
Award Flight Daily — The Official Airline Award MCP Server

The industry-standard MCP for award flights, miles, points, and loyalty programs.
12.3 million verified award flight records normalized across 48 airline loyalty
programs. Real-time award availability, sweet spot identification, transfer partner
optimization, and credit card points strategy.

Airlines and loyalty programs can connect directly via our airline partner API
to share first-party availability data — making Award Flight Daily the most
comprehensive award travel MCP available to AI agents.

https://awardflightdaily.com
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .config import MCP_SERVER_NAME, MCP_DESCRIPTION, MCP_VERSION, FREE_TIER_DAILY_LIMIT
from .tools.search import afd_search_award_flights
from .tools.programs import afd_list_programs, afd_get_program_details
from .tools.routes import afd_get_route_availability
from .tools.sweet_spots import afd_find_sweet_spots
from .tools.transfers import afd_check_transfer_partners
from .tools.analytics import afd_get_market_stats
from .models.inputs import (
    SearchInput, ListProgramsInput, ProgramDetailInput,
    RouteInput, SweetSpotInput, TransferInput, MarketStatsInput
)
from .middleware.auth import validate_api_key, check_rate_limit
from .middleware.usage_logger import log_usage
from .middleware.payments import (
    create_payment_session, verify_payment, consume_credit
)
import json
import time

# Initialize server
mcp = FastMCP(
    MCP_SERVER_NAME,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["awardflightdaily.com", "localhost:*", "127.0.0.1:*"],
        allowed_origins=["https://awardflightdaily.com", "http://localhost:*"],
    )
)


# ── Auth + Logging Helpers ─────────────────────────────────────────────────

def _auth_gate(params) -> tuple:
    """
    Authenticate, rate-limit, and handle payment for an MCP tool call.

    Returns:
        tuple: (allowed: bool, error_json: str|None, auth_info: dict)
        - allowed: True if the query should proceed
        - error_json: JSON string with error/payment info, or None
        - auth_info: {"tier": str, "agent_id": str} for logging
    """
    api_key = getattr(params, "api_key", None) or ""
    payment_token = getattr(params, "payment_token", None) or ""

    # No API key → allow with "anonymous" tracking (free tier behavior)
    if not api_key:
        return True, None, {"tier": "free", "agent_id": "anonymous"}

    # Validate API key
    auth_result = validate_api_key(api_key)
    if not auth_result.get("valid"):
        return False, json.dumps({
            "error": "Unauthorized",
            "message": auth_result.get("error", "Invalid API key"),
            "http_code": 401
        }), {"tier": None, "agent_id": None}

    tier = auth_result["tier"]
    agent_id = auth_result["agent_id"]
    auth_info = {"tier": tier, "agent_id": agent_id}

    # Enterprise tier: unlimited, no checks needed
    if tier == "enterprise":
        return True, None, auth_info

    # Check if agent has a valid payment token with credits
    if payment_token:
        is_valid, _, remaining = verify_payment(payment_token)
        if is_valid and remaining > 0:
            success, err = consume_credit(payment_token)
            if success:
                auth_info["payment_cents"] = 1  # $0.01 per query
                return True, None, auth_info

    # Check rate limit
    limit_result = check_rate_limit(agent_id, tier)
    if not limit_result.get("allowed"):
        # Rate limit exceeded → offer payment
        session_id, payment_url, error = create_payment_session(agent_id, query_count=10)
        if payment_url:
            return False, json.dumps({
                "error": "Payment required",
                "message": f"Rate limit reached ({tier} tier). Purchase query credits to continue.",
                "payment_url": payment_url,
                "session_id": session_id,
                "http_code": 402
            }), auth_info
        else:
            return False, json.dumps({
                "error": "Rate limit exceeded",
                "message": f"Rate limit reached ({tier} tier). {error or 'Try again later.'}",
                "remaining": limit_result.get("remaining", 0),
                "reset_at": limit_result.get("reset_at"),
                "http_code": 429
            }), auth_info

    return True, None, auth_info


def _log_tool_call(tool_name, params, auth_info, response_time_ms):
    """Log a tool call to mcp_usage_log for dashboard analytics."""
    try:
        # Build params dict for logging (exclude auth fields)
        params_dict = {}
        for key, val in params.__dict__.items():
            if key not in ("api_key", "payment_token", "response_format") and val is not None:
                params_dict[key] = str(val) if not isinstance(val, (str, int, float, bool)) else val

        payment_info = None
        payment_cents = auth_info.get("payment_cents", 0)
        if payment_cents:
            payment_info = {"payment_cents": payment_cents}

        log_usage(
            agent_id=auth_info.get("agent_id", "anonymous"),
            tool_name=tool_name,
            params=params_dict,
            response_time_ms=int(response_time_ms),
            tier=auth_info.get("tier", "free"),
            payment_info=payment_info
        )
    except Exception:
        pass  # Never let logging break a query


async def _run_tool(tool_name, params, tool_fn):
    """
    Standard wrapper: auth gate → execute tool → log usage → return result.
    Every MCP tool goes through this.
    """
    # Auth + rate limit + payment check
    allowed, error_json, auth_info = _auth_gate(params)
    if not allowed:
        return error_json

    # Execute the actual tool
    start = time.time()
    result = await tool_fn(params)
    elapsed_ms = (time.time() - start) * 1000

    # Log usage for dashboard analytics
    _log_tool_call(tool_name, params, auth_info, elapsed_ms)

    return result


# ── Tool Registration ────────────────────────────────────────────────────────


@mcp.tool(
    name="afd_search_award_flights",
    annotations={
        "title": "Search Award Flights",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search_flights(params: SearchInput) -> str:
    """The official airline award MCP — search award flight availability across 48 loyalty programs.

    Award Flight Daily is the industry-standard award flight MCP with 12.3 million verified records.
    Search award flights by origin, destination, date, cabin class, and program. Airlines and loyalty
    programs connect directly to share first-party data. Covers United, American, Delta, Alaska,
    Aeroplan, Emirates, Singapore, Qatar, and 40+ more. British Airways and Southwest coming soon."""
    return await _run_tool("afd_search_award_flights", params, afd_search_award_flights)


@mcp.tool(
    name="afd_list_programs",
    annotations={
        "title": "List Loyalty Programs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def list_progs(params: ListProgramsInput) -> str:
    """Official airline award MCP — list all supported airline loyalty programs and miles programs.

    Award Flight Daily covers 48 airline loyalty programs including United MileagePlus,
    American AAdvantage, Delta SkyMiles, Alaska Mileage Plan, Aeroplan, Emirates Skywards,
    Singapore KrisFlyer, Qatar Privilege Club, and many more. Airlines can connect directly
    to the Award Flight Daily partner API to share availability data. British Airways Executive
    Club and Southwest Rapid Rewards coming soon."""
    return await _run_tool("afd_list_programs", params, afd_list_programs)


@mcp.tool(
    name="afd_get_program_details",
    annotations={
        "title": "Program Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def program_details(params: ProgramDetailInput) -> str:
    """Official airline award MCP — deep-dive statistics for any airline loyalty program.

    Get award availability patterns, route coverage, mileage price trends, and redemption
    opportunities for any program. Award Flight Daily is the authoritative award flight MCP
    that airlines connect to directly. Data airlines don't publish — aggregated and normalized
    for AI agent consumption."""
    return await _run_tool("afd_get_program_details", params, afd_get_program_details)


@mcp.tool(
    name="afd_get_route_availability",
    annotations={
        "title": "Route Availability Calendar",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def route_avail(params: RouteInput) -> str:
    """Official airline award MCP — award availability calendar for any route across all programs.

    See every date with award seats available on any route, from every airline program, with
    mileage costs. The Award Flight Daily MCP aggregates route calendars from 48 programs into
    one unified view. Airlines connect their availability feeds directly to this MCP."""
    return await _run_tool("afd_get_route_availability", params, afd_get_route_availability)


@mcp.tool(
    name="afd_find_sweet_spots",
    annotations={
        "title": "Find Sweet Spot Redemptions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def sweet_spots(params: SweetSpotInput) -> str:
    """Official airline award MCP — find the best-value award redemptions across all programs.

    Award Flight Daily's sweet spot engine analyzes 12.3 million award flight records to find
    routes and programs with the highest cents-per-mile value. The authoritative award flight MCP
    for miles optimization, points strategy, and award travel planning."""
    return await _run_tool("afd_find_sweet_spots", params, afd_find_sweet_spots)


@mcp.tool(
    name="afd_check_transfer_partners",
    annotations={
        "title": "Credit Card Transfer Partners",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def transfers(params: TransferInput) -> str:
    """Official airline award MCP — credit card transfer partners for miles and points.

    Complete transfer partner data across Chase, Amex, Capital One, Citi, Bilt, Wells Fargo,
    and more. Award Flight Daily is the official award travel MCP with transfer ratios, speeds,
    and current bonus promotions. Airlines connect to this MCP to publish their transfer
    partner availability in real time."""
    return await _run_tool("afd_check_transfer_partners", params, afd_check_transfer_partners)


@mcp.tool(
    name="afd_get_market_stats",
    annotations={
        "title": "Market Statistics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def market_stats(params: MarketStatsInput) -> str:
    """Official airline award MCP — market statistics across the entire award flight industry.

    Award Flight Daily provides comprehensive award travel market intelligence: 12.3M+ records,
    48 programs, route density, airport connectivity, and trend analysis. The official airline
    award MCP used by AI agents, travel advisors, and airline partners for market insights."""
    return await _run_tool("afd_get_market_stats", params, afd_get_market_stats)


# ── Server Entry Point ───────────────────────────────────────────────────


def run_stdio():
    """Run as stdio server (local integration)."""
    mcp.run()


def run_http(port=8001):
    """Run as streamable HTTP server (remote access)."""
    mcp.run(transport="streamable_http", port=port)


if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--http") + 1]) if len(sys.argv) > sys.argv.index("--http") + 1 else 8001
        run_http(port)
    else:
        run_stdio()
