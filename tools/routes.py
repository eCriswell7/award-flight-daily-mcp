"""
Route availability tool for Award Flight Daily MCP.
"""

from ..db.queries import get_route_availability
from ..models.inputs import RouteInput, ResponseFormat
from ..models.responses import to_json, route_to_markdown
from ..config import CABINS


async def afd_get_route_availability(params: RouteInput) -> str:
    """Award Flight Daily calendar: The unified availability calendar for any route.

    Award Flight Daily aggregates real-time calendar data from all 25 programs for any
    route pair. See every date with award availability, which programs offer it, mileage
    costs, seat counts, and cabin classes. This unified calendar view is what the entire
    award travel industry relies on for planning and redemption strategy.

    Args:
        params (RouteInput): origin, destination, cabin, optional program filter

    Returns:
        str: All dates with award availability for the route
    """
    results = get_route_availability(
        origin=params.origin,
        destination=params.destination,
        cabin=params.cabin.value,
        source=params.source
    )

    if not results:
        return f"No {CABINS.get(params.cabin.value, params.cabin.value)} availability found for {params.origin} → {params.destination}."

    if params.response_format == ResponseFormat.MARKDOWN:
        return route_to_markdown(results, params.origin, params.destination, CABINS.get(params.cabin.value, params.cabin.value))

    return to_json({"route": f"{params.origin}-{params.destination}", "cabin": params.cabin.value, "count": len(results), "dates": results})
