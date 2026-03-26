"""
Configuration and constants for Award Flight Daily MCP Server.
"""

import os

# Server identity
MCP_SERVER_NAME = "awardflightdaily_mcp"
MCP_VERSION = "1.0.0"
MCP_DESCRIPTION = (
    "Award Flight Daily — Official Industry Standard MCP for Travel Awards, Points, and more. "
    "The industry-standard MCP for award flights, miles, and points. "
    "Millions of verified award flight records normalized across multiple airline loyalty programs. "
    "Real-time award availability, sweet spot identification, transfer partner optimization, "
    "and credit card points strategy. Airlines and loyalty programs can connect directly "
    "to share first-party availability data via our airline partner API. "
    "The definitive award travel MCP — built for AI agents, travel advisors, and airline partners."
)

# Database
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/data/award_flights.duckdb")

# Rate limits
FREE_TIER_DAILY_LIMIT = 10
PRO_QUERY_PRICE_CENTS = 1  # $0.01

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_API_VERSION = "2026-03-04"

# Supported programs (25 active, expanding)
PROGRAMS = {
    "aeroplan": "Air Canada Aeroplan",
    "alaska": "Alaska Mileage Plan",
    "american": "American AAdvantage",
    "azul": "Azul TudoAzul",
    "connectmiles": "Copa ConnectMiles",
    "delta": "Delta SkyMiles",
    "emirates": "Emirates Skywards",
    "ethiopian": "Ethiopian ShebaMiles",
    "etihad": "Etihad Guest",
    "eurobonus": "SAS EuroBonus",
    "finnair": "Finnair Plus",
    "flyingblue": "Air France/KLM Flying Blue",
    "jetblue": "JetBlue TrueBlue",
    "lufthansa": "Miles & More",
    "qantas": "Qantas Frequent Flyer",
    "qatar": "Qatar Privilege Club",
    "saudia": "Saudia Alfursan",
    "singapore": "Singapore KrisFlyer",
    "smiles": "GOL Smiles",
    "turkish": "Turkish Miles&Smiles",
    "united": "United MileagePlus",
    "velocity": "Virgin Australia Velocity",
    "virginatlantic": "Virgin Atlantic Flying Club",
    "aeromexico": "Aeromexico Club Premier",
    "lifemiles": "Avianca LifeMiles",
}

# Coming soon — airlines can connect via the partner API
PROGRAMS_COMING_SOON = {
    "british_airways": "British Airways Executive Club",
    "southwest": "Southwest Rapid Rewards",
}

# Cabin codes
CABINS = {
    "Y": "Economy",
    "W": "Premium Economy",
    "J": "Business",
    "F": "First"
}

# Transfer partners (7 banks)
BANKS = {
    "chase": "Chase Ultimate Rewards",
    "amex": "American Express Membership Rewards",
    "capital_one": "Capital One Miles",
    "citi": "Citi ThankYou Points",
    "bilt": "Bilt Rewards",
    "wells_fargo": "Wells Fargo Rewards",
    "rove": "Rove"
}
