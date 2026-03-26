# Award Flight Daily MCP Server

A FastMCP server that wraps the Award Flight Daily database (12.3M award flight records across 25 loyalty programs) and exposes it to AI agents via tools.

## Overview

The Award Flight Daily MCP server provides 7 core tools for searching, analyzing, and optimizing award travel:

1. **afd_search_award_flights** - Core search across 12M+ records
2. **afd_list_programs** - All 25 programs with statistics
3. **afd_get_program_details** - Deep dive on a single program
4. **afd_get_route_availability** - Calendar view for a route
5. **afd_find_sweet_spots** - Best-value redemptions
6. **afd_check_transfer_partners** - Credit card transfer ratios
7. **afd_get_market_stats** - Aggregate database statistics

## File Structure

```
mcp_server/
├── __init__.py                 # Package definition
├── config.py                   # Constants: programs, cabins, banks
├── server.py                   # FastMCP server entry point (7 tools registered)
├── db/
│   ├── __init__.py
│   └── queries.py             # DuckDB queries (read-only, parameterized)
├── models/
│   ├── __init__.py
│   ├── inputs.py              # 8 Pydantic input models with validators
│   └── responses.py           # Formatting helpers (JSON/Markdown)
└── tools/
    ├── __init__.py
    ├── search.py              # afd_search_award_flights
    ├── programs.py            # afd_list_programs, afd_get_program_details
    ├── routes.py              # afd_get_route_availability
    ├── sweet_spots.py         # afd_find_sweet_spots
    ├── transfers.py           # afd_check_transfer_partners
    └── analytics.py           # afd_get_market_stats
```

## Configuration

All environment and program configuration lives in `config.py`:

- **MCP_SERVER_NAME**: "awardflightdaily_mcp"
- **DUCKDB_PATH**: Environment variable, defaults to `/data/award_flights.duckdb`
- **PROGRAMS**: Dictionary of 25 programs (slug -> full name)
- **CABINS**: Cabin class codes (Y/W/J/F)
- **BANKS**: 7 credit card programs

## Installation & Deployment

### Requirements

```
fastmcp>=1.0.0
pydantic>=2.0
duckdb==1.1.3
```

### Running

Stdio mode (local):
```bash
python -m mcp_server.server
```

HTTP mode (remote):
```bash
python -m mcp_server.server --http 8001
```

## Tools API

### 1. Search Award Flights

```python
SearchInput(
    origin="JFK",                      # Required: IATA code(s)
    destination="NRT",                 # Required: IATA code(s)
    date_from="2026-06-01",           # Required: YYYY-MM-DD
    date_to="2026-06-30",             # Required: YYYY-MM-DD
    cabin=CabinClass.BUSINESS,        # Optional: Y/W/J/F (default J)
    source="united,aeroplan",         # Optional: program filter
    direct_only=False,                # Optional: nonstop only
    max_miles=100000,                 # Optional: mileage cap
    min_seats=1,                      # Optional: min seats (default 1)
    limit=50,                         # Optional: results limit (default 50, max 200)
    offset=0,                         # Optional: pagination offset
    response_format=ResponseFormat.JSON # Optional: JSON or Markdown
)
```

Returns: Paginated flight results with mileage, taxes, seats, airlines, equipment.

### 2. List Programs

```python
ListProgramsInput(
    response_format=ResponseFormat.JSON
)
```

Returns: All 25 programs with:
- Total flights & routes
- Date range
- Cabin availability counts (Y/W/J/F)

### 3. Program Details

```python
ProgramDetailInput(
    program="united",  # Required: program slug
    response_format=ResponseFormat.JSON
)
```

Returns: Deep stats for one program:
- Total availability
- Unique routes & airports
- Average & minimum mileage by cabin

### 4. Route Availability

```python
RouteInput(
    origin="JFK",
    destination="NRT",
    cabin=CabinClass.BUSINESS,
    source=None,  # Optional: filter by program
    response_format=ResponseFormat.JSON
)
```

Returns: All dates for a route with mileage, taxes, seats per program.

### 5. Find Sweet Spots

```python
SweetSpotInput(
    cabin=CabinClass.BUSINESS,
    origin=None,  # Optional
    destination=None,  # Optional
    limit=25,
    response_format=ResponseFormat.JSON
)
```

Returns: Best-value routes ranked by minimum mileage cost.

### 6. Transfer Partners

```python
TransferInput(
    bank="chase",      # Optional: bank slug
    program="united",  # Optional: program slug
    response_format=ResponseFormat.JSON
)
```

Returns: Credit card → airline transfer mappings with:
- Transfer ratio (e.g., "1:1")
- Speed (e.g., "Instant", "1-2 days")

### 7. Market Stats

```python
MarketStatsInput(
    response_format=ResponseFormat.JSON
)
```

Returns: Aggregate database stats:
- Total records, programs, routes
- Airport coverage
- Cabin availability breakdown

## Input Validation

All inputs use Pydantic with validation:

- **IATA codes**: Must be exactly 3 alphabetic characters
- **Dates**: YYYY-MM-DD format only
- **Cabin**: Enum restricted to Y/W/J/F
- **Limit**: 1-200 results
- **Offset**: >= 0
- **Min seats**: 1-9

Invalid inputs raise `ValidationError` with detailed messages.

## Response Formats

### JSON (default)

Full structured response with pagination metadata:

```json
{
  "total": 1234,
  "count": 50,
  "offset": 0,
  "has_more": true,
  "cabin": "J",
  "results": [
    {
      "id": "...",
      "source": "united",
      "origin": "JFK",
      "destination": "NRT",
      "date": "2026-06-15",
      "mileage": 75000,
      "taxes": 11.20,
      "seats": 2,
      "direct": true,
      "airlines": "United",
      "equipment": "B787",
      "updated_at": "2026-03-26T12:34:56"
    }
  ]
}
```

### Markdown

Human-readable output with formatting:

```markdown
# Award Flight Search Results

**1234 flights found** | Cabin: Business | Showing 50

## JFK → NRT | 2026-06-15

- **75,000 miles** + $11.20 taxes | united
- Nonstop | 2 seats | United B787

...
```

## Database

All queries are:
- **Read-only** (DuckDB in read-only mode)
- **Parameterized** with proper escaping
- **Filtered** on `expired_at IS NULL` (active records only)
- **Type-safe** with CAST(? AS DATE) for dates

Connection is lazy-loaded on first query and reused.

## Design Principles

1. **No monoliths** - Each tool in its own module
2. **Separation of concerns** - DB queries, models, tools, responses separate
3. **Type safety** - Pydantic models on all inputs
4. **Defensive** - All parameterized queries, validators on inputs
5. **Fast** - Read-only DuckDB, lazy connection, caching via MCP layer
6. **Testable** - Pure functions, no side effects

## Error Handling

- Invalid input: Pydantic `ValidationError` with field details
- Database error: Returns error message string (no 500s)
- No results: Friendly "No flights found" message

The MCP layer handles serialization of errors to the client.

## Future Enhancements

- Price tracking ($/mile value calculation)
- Seat map integration
- Award chart comparison
- Frequent flyer earning rates
- Stopover/layover optimization
- Alert setup via MCP (future: read-write tools)
