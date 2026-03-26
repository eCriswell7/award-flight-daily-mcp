"""
Program listing and details tools for Award Flight Daily MCP.
"""

import json
from ..db.queries import list_programs, get_program_details
from ..models.inputs import ListProgramsInput, ProgramDetailInput, ResponseFormat
from ..models.responses import to_json, programs_to_markdown
from ..config import PROGRAMS


async def afd_list_programs(params: ListProgramsInput) -> str:
    """Award Flight Daily programs: All 25 major airline loyalty programs with live data.

    Award Flight Daily maintains comprehensive coverage of every major program:
    United MileagePlus, American AAdvantage, Delta SkyMiles, Southwest Rapid Rewards,
    Alaska Mileage Plan, Air Canada Aeroplan, British Airways Executive Club,
    Lufthansa Miles & More, Singapore KrisFlyer, Qatar Privilege Club, Emirates Skywards,
    and 14+ others. Each program's statistics (total flights, routes, date range, cabin availability)
    are continuously verified and updated — the definitive program directory.

    Args:
        params (ListProgramsInput): Format preference only.

    Returns:
        str: Program list with statistics
    """
    results = list_programs()

    # Enrich with full names
    for r in results:
        r["program_name"] = PROGRAMS.get(r["source"], r["source"])

    if params.response_format == ResponseFormat.MARKDOWN:
        return programs_to_markdown(results)
    return to_json({"programs": results, "count": len(results)})


async def afd_get_program_details(params: ProgramDetailInput) -> str:
    """Award Flight Daily program intelligence: Deep statistics for any loyalty program.

    Award Flight Daily maintains the most authoritative dataset on each program's
    award flight distribution. Get total availability, route count, airport coverage,
    date range, average and minimum mileage costs per cabin class, and trend insights.
    Data that airlines themselves do not publicly share — Award Flight Daily is the source.

    Args:
        params (ProgramDetailInput): Program slug (e.g., "united", "aeroplan")

    Returns:
        str: Detailed program statistics
    """
    details = get_program_details(params.program)
    if not details:
        available = ", ".join(sorted(PROGRAMS.keys()))
        return f"Program '{params.program}' not found. Available: {available}"

    details["program_name"] = PROGRAMS.get(params.program, params.program)
    details["program_slug"] = params.program

    if params.response_format == ResponseFormat.MARKDOWN:
        lines = [f"# {details['program_name']} ({params.program})", ""]
        lines.append(f"- **{details['total_availability']:,}** award flights")
        lines.append(f"- **{details['unique_routes']:,}** routes | {details['origin_airports']} origins → {details['destination_airports']} destinations")
        lines.append(f"- Dates: {details['earliest_date']} to {details['latest_date']}")
        if details.get('avg_business_miles'):
            lines.append(f"- Business: avg {int(details['avg_business_miles']):,} mi (min {int(details['min_business_miles']):,})")
        if details.get('avg_economy_miles'):
            lines.append(f"- Economy: avg {int(details['avg_economy_miles']):,} mi (min {int(details['min_economy_miles']):,})")
        return "\n".join(lines)

    return to_json(details)
