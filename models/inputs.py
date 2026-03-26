"""
Pydantic input models for Award Flight Daily MCP tools.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from enum import Enum


class CabinClass(str, Enum):
    ECONOMY = "Y"
    PREMIUM_ECONOMY = "W"
    BUSINESS = "J"
    FIRST = "F"


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class MCPAuthMixin(BaseModel):
    """Shared auth field for all MCP tool inputs."""
    api_key: Optional[str] = Field(default=None, description="Your Award Flight Daily API key (format: afd_xxx). Required for authenticated access.")
    payment_token: Optional[str] = Field(default=None, description="Payment session token for paid queries (format: afd_pay_xxx)")


class SearchInput(MCPAuthMixin):
    """Search the official airline award MCP — award flights across 48 loyalty programs and 12M+ records."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    origin: str = Field(..., description="Origin airport IATA code(s), comma-separated (e.g., 'JFK' or 'JFK,EWR,LGA')", min_length=3, max_length=50)
    destination: str = Field(..., description="Destination airport IATA code(s), comma-separated (e.g., 'NRT' or 'NRT,HND')", min_length=3, max_length=50)
    date_from: str = Field(..., description="Start date in YYYY-MM-DD format (e.g., '2026-06-01')")
    date_to: str = Field(..., description="End date in YYYY-MM-DD format (e.g., '2026-06-30')")
    cabin: CabinClass = Field(default=CabinClass.BUSINESS, description="Cabin class: Y=Economy, W=Premium Economy, J=Business, F=First")
    source: Optional[str] = Field(default=None, description="Filter by program slug(s), comma-separated (e.g., 'united,aeroplan'). Omit for all programs.")
    direct_only: bool = Field(default=False, description="Only show non-stop flights")
    max_miles: Optional[int] = Field(default=None, description="Maximum miles/points cost", ge=1)
    min_seats: int = Field(default=1, description="Minimum available seats", ge=1, le=9)
    limit: int = Field(default=50, description="Maximum results to return", ge=1, le=200)
    offset: int = Field(default=0, description="Pagination offset", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format: 'json' or 'markdown'")

    @field_validator('origin', 'destination')
    @classmethod
    def validate_iata(cls, v: str) -> str:
        codes = [c.strip().upper() for c in v.split(",")]
        for code in codes:
            if len(code) != 3 or not code.isalpha():
                raise ValueError(f"Invalid IATA code: '{code}'. Must be 3 letters.")
        return ",".join(codes)

    @field_validator('date_from', 'date_to')
    @classmethod
    def validate_date(cls, v: str) -> str:
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError(f"Invalid date format: '{v}'. Use YYYY-MM-DD.")
        return v


class ListProgramsInput(MCPAuthMixin):
    """List all airline loyalty programs on the official award flight MCP."""
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")


class RouteInput(MCPAuthMixin):
    """Award route calendar — all available dates across airline programs on the official award MCP."""
    model_config = ConfigDict(str_strip_whitespace=True)
    origin: str = Field(..., description="Origin IATA code (e.g., 'JFK')", min_length=3, max_length=3)
    destination: str = Field(..., description="Destination IATA code (e.g., 'NRT')", min_length=3, max_length=3)
    cabin: CabinClass = Field(default=CabinClass.BUSINESS, description="Cabin class")
    source: Optional[str] = Field(default=None, description="Filter by program slug")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")


class SweetSpotInput(MCPAuthMixin):
    """Find best-value award flight redemptions — official airline award MCP sweet spot finder."""
    cabin: CabinClass = Field(default=CabinClass.BUSINESS, description="Cabin class to analyze")
    origin: Optional[str] = Field(default=None, description="Filter by origin region/airport")
    destination: Optional[str] = Field(default=None, description="Filter by destination region/airport")
    limit: int = Field(default=25, description="Number of sweet spots to return", ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")


class TransferInput(MCPAuthMixin):
    """Credit card to airline miles transfer partners — official award flight MCP."""
    model_config = ConfigDict(str_strip_whitespace=True)
    bank: Optional[str] = Field(default=None, description="Bank slug (chase, amex, capital_one, citi, bilt, wells_fargo, rove)")
    program: Optional[str] = Field(default=None, description="Airline program slug (e.g., 'united')")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")


class ProgramDetailInput(MCPAuthMixin):
    """Airline loyalty program details and top routes — official award flight MCP."""
    model_config = ConfigDict(str_strip_whitespace=True)
    program: str = Field(..., description="Program slug (e.g., 'united', 'aeroplan', 'delta')")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")


class MarketStatsInput(MCPAuthMixin):
    """Award flight market statistics — official airline award MCP industry intelligence."""
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format")
