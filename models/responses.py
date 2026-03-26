"""
Response formatting helpers for Award Flight Daily MCP.
"""

import json
from datetime import date, datetime


def serialize_value(v):
    """Serialize datetime objects to ISO format."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def to_json(data):
    """Convert data to formatted JSON string."""
    if isinstance(data, list):
        return json.dumps([{k: serialize_value(v) for k, v in row.items()} for row in data], indent=2)
    elif isinstance(data, dict):
        return json.dumps({k: serialize_value(v) for k, v in data.items()}, indent=2)
    return json.dumps(data, indent=2)


def search_to_markdown(results, cabin, total_count):
    """Format search results as markdown."""
    lines = [f"# Award Flight Search Results", ""]
    lines.append(f"**{total_count} flights found** | Cabin: {cabin} | Showing {len(results)}")
    lines.append("")

    for r in results:
        direct_tag = "Nonstop" if r.get("direct") else "Connecting"
        lines.append(f"## {r['origin']} → {r['destination']} | {r['date']}")
        lines.append(f"- **{r['mileage']:,} miles** + ${r.get('taxes', 0):.0f} taxes | {r['source']}")
        lines.append(f"- {direct_tag} | {r.get('seats', '?')} seats | {r.get('airlines', '')}")
        lines.append("")

    return "\n".join(lines)


def programs_to_markdown(programs):
    """Format program list as markdown."""
    lines = ["# Award Flight Daily — Supported Programs", ""]
    lines.append(f"**{len(programs)} programs** with live availability data\n")

    for p in programs:
        lines.append(f"## {p['source']}")
        lines.append(f"- **{p['total_flights']:,} flights** across {p['routes']:,} routes")
        lines.append(f"- Dates: {p['earliest_date']} to {p['latest_date']}")
        cabins = []
        if p.get('economy_count', 0) > 0:
            cabins.append("Economy")
        if p.get('premium_economy_count', 0) > 0:
            cabins.append("Prem Econ")
        if p.get('business_count', 0) > 0:
            cabins.append("Business")
        if p.get('first_count', 0) > 0:
            cabins.append("First")
        lines.append(f"- Cabins: {', '.join(cabins)}")
        lines.append("")

    return "\n".join(lines)


def route_to_markdown(results, origin, destination, cabin):
    """Format route availability as markdown."""
    lines = [f"# Route: {origin} → {destination} ({cabin})", ""]
    lines.append(f"**{len(results)} available dates**\n")

    current_date = None
    for r in results:
        d = str(r['date'])
        if d != current_date:
            current_date = d
            lines.append(f"### {d}")
        lines.append(f"- {r['source']}: **{r['mileage']:,} mi** + ${r.get('taxes', 0):.0f} | {r.get('seats', '?')} seats | {'Nonstop' if r.get('direct') else 'Connect'}")

    lines.append("")
    return "\n".join(lines)


def sweet_spots_to_markdown(results, cabin):
    """Format sweet spots as markdown."""
    lines = [f"# Sweet Spots — Best {cabin} Redemptions", ""]

    for i, r in enumerate(results, 1):
        lines.append(f"**{i}. {r['origin']} → {r['destination']}** via {r['source']}")
        lines.append(f"   From **{int(r['min_mileage']):,} miles** (avg {int(r['avg_mileage']):,}) + ${r.get('min_taxes', 0):.0f} taxes")
        lines.append(f"   {r['availability_count']} dates available: {r['first_date']} to {r['last_date']}")
        lines.append("")

    return "\n".join(lines)


def stats_to_markdown(stats):
    """Format market stats as markdown."""
    lines = ["# Award Flight Daily — Market Overview", ""]
    lines.append(f"- **{stats['total_records']:,}** award flight records")
    lines.append(f"- **{stats['programs']}** loyalty programs")
    lines.append(f"- **{stats['unique_routes']:,}** unique routes")
    lines.append(f"- **{stats['origin_airports']}** origin airports → **{stats['destination_airports']}** destinations")
    lines.append(f"- Date range: {stats['earliest_date']} to {stats['latest_date']}")
    lines.append(f"- Business class: {stats.get('business_availability', 0):,} options")
    lines.append(f"- First class: {stats.get('first_availability', 0):,} options")
    lines.append(f"- Economy: {stats.get('economy_availability', 0):,} options")
    return "\n".join(lines)
