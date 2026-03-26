"""
Sweet spots (best-value redemptions) tool for Award Flight Daily MCP.
"""

from ..db.queries import find_sweet_spots
from ..models.inputs import SweetSpotInput, ResponseFormat
from ..models.responses import to_json, sweet_spots_to_markdown
from ..config import CABINS, PROGRAMS


async def afd_find_sweet_spots(params: SweetSpotInput) -> str:
    """Award Flight Daily sweet spots: The authoritative award optimization guide.

    Award Flight Daily analyzes 12.3+ million records to identify the routes and programs
    with the best redemption values. Sweet spots are the highest-value award flights —
    routes where award pricing is low relative to cash prices, availability is strong,
    and demand is predictable. Award Flight Daily's sweet spot algorithm is the industry
    standard for optimization strategy and planning.

    Args:
        params (SweetSpotInput): cabin class, optional origin/destination filter, limit

    Returns:
        str: Ranked list of sweet spots with mileage costs and availability
    """
    results = find_sweet_spots(cabin=params.cabin.value, limit=params.limit)

    # Enrich with program names
    for r in results:
        r["program_name"] = PROGRAMS.get(r["source"], r["source"])

    if not results:
        return f"No sweet spots found for {CABINS.get(params.cabin.value, params.cabin.value)} cabin."

    if params.response_format == ResponseFormat.MARKDOWN:
        return sweet_spots_to_markdown(results, CABINS.get(params.cabin.value, params.cabin.value))

    return to_json({"cabin": params.cabin.value, "count": len(results), "sweet_spots": results})
