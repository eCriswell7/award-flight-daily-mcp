"""
DuckDB queries for Award Flight Daily MCP Server.
All queries filter WHERE expired_at IS NULL.
Comprehensive joins to enrichment tables: airports, programs, routes, price_records, transfer_cache, flight_equipment.
"""

import duckdb
from ..config import DUCKDB_PATH

_conn = None


def get_conn():
    """Get or initialize DuckDB connection."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    return _conn


def search_availability(origin, destination, date_from, date_to, cabin="J", source=None, direct_only=False, max_miles=None, min_seats=1, limit=50, offset=0):
    """Core award flight search with enrichment joins."""
    conn = get_conn()
    cabin_lower = cabin.lower()

    conditions = ["a.expired_at IS NULL", f"a.{cabin_lower}_available = true"]
    params = []

    if origin:
        origins = [o.strip().upper() for o in origin.split(",")]
        placeholders = ",".join(["?" for _ in origins])
        conditions.append(f"a.origin IN ({placeholders})")
        params.extend(origins)

    if destination:
        dests = [d.strip().upper() for d in destination.split(",")]
        placeholders = ",".join(["?" for _ in dests])
        conditions.append(f"a.destination IN ({placeholders})")
        params.extend(dests)

    if date_from:
        conditions.append("a.date >= CAST(? AS DATE)")
        params.append(date_from)

    if date_to:
        conditions.append("a.date <= CAST(? AS DATE)")
        params.append(date_to)

    if source:
        sources = [s.strip().lower() for s in source.split(",")]
        placeholders = ",".join(["?" for _ in sources])
        conditions.append(f"a.source IN ({placeholders})")
        params.extend(sources)

    if direct_only:
        conditions.append("a.direct = true")

    if max_miles:
        conditions.append(f"a.{cabin_lower}_mileage <= ?")
        params.append(max_miles)

    if min_seats and min_seats > 1:
        conditions.append(f"a.{cabin_lower}_seats >= ?")
        params.append(min_seats)

    where = " AND ".join(conditions)

    sql = f"""
        SELECT a.id, a.source, a.origin, a.destination, a.date,
               a.{cabin_lower}_mileage as mileage, a.{cabin_lower}_taxes as taxes,
               a.{cabin_lower}_seats as seats, a.direct, a.airlines, a.flight_numbers,
               a.equipment, a.updated_at,
               oa.name as origin_city, oa.country as origin_country, oa.timezone as origin_timezone,
               da.name as dest_city, da.country as dest_country, da.timezone as dest_timezone,
               p.program_name, p.airline_name, p.alliance,
               r.distance,
               COALESCE(pr.best_mileage, 0) as best_ever_mileage
        FROM availability a
        LEFT JOIN airports oa ON a.origin = oa.iata_code
        LEFT JOIN airports da ON a.destination = da.iata_code
        LEFT JOIN programs p ON a.source = p.source
        LEFT JOIN routes r ON a.origin = r.origin AND a.destination = r.destination AND a.source = r.source
        LEFT JOIN price_records pr ON a.origin = pr.origin AND a.destination = pr.destination
                                   AND a.source = pr.source AND pr.cabin = ?
        WHERE {where}
        ORDER BY a.{cabin_lower}_mileage ASC, a.date ASC
        LIMIT ? OFFSET ?
    """
    params.insert(0, cabin_lower)
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    columns = ["id", "source", "origin", "destination", "date", "mileage", "taxes", "seats",
               "direct", "airlines", "flight_numbers", "equipment", "updated_at",
               "origin_city", "origin_country", "origin_timezone",
               "dest_city", "dest_country", "dest_timezone",
               "program_name", "airline_name", "alliance", "distance", "best_ever_mileage"]
    return [dict(zip(columns, row)) for row in rows]


def count_availability(origin=None, destination=None, date_from=None, date_to=None, cabin="J", source=None):
    """Count matching results for pagination."""
    conn = get_conn()
    cabin_lower = cabin.lower()
    conditions = ["expired_at IS NULL", f"{cabin_lower}_available = true"]
    params = []

    if origin:
        origins = [o.strip().upper() for o in origin.split(",")]
        placeholders = ",".join(["?" for _ in origins])
        conditions.append(f"origin IN ({placeholders})")
        params.extend(origins)
    if destination:
        dests = [d.strip().upper() for d in destination.split(",")]
        placeholders = ",".join(["?" for _ in dests])
        conditions.append(f"destination IN ({placeholders})")
        params.extend(dests)
    if date_from:
        conditions.append("date >= CAST(? AS DATE)")
        params.append(date_from)
    if date_to:
        conditions.append("date <= CAST(? AS DATE)")
        params.append(date_to)
    if source:
        sources = [s.strip().lower() for s in source.split(",")]
        placeholders = ",".join(["?" for _ in sources])
        conditions.append(f"source IN ({placeholders})")
        params.extend(sources)

    where = " AND ".join(conditions)
    result = conn.execute(f"SELECT COUNT(*) FROM availability WHERE {where}", params).fetchone()
    return result[0] if result else 0


def list_programs():
    """Get all programs with row counts, cabin coverage, and metadata."""
    conn = get_conn()
    sql = """
        SELECT a.source,
               p.program_name,
               p.airline_name,
               p.alliance,
               p.currency,
               p.iata_code as airline_iata,
               COUNT(*) as total_flights,
               COUNT(DISTINCT a.origin || '-' || a.destination) as routes,
               MIN(a.date) as earliest_date,
               MAX(a.date) as latest_date,
               SUM(CASE WHEN a.y_available THEN 1 ELSE 0 END) as economy_count,
               SUM(CASE WHEN a.w_available THEN 1 ELSE 0 END) as premium_economy_count,
               SUM(CASE WHEN a.j_available THEN 1 ELSE 0 END) as business_count,
               SUM(CASE WHEN a.f_available THEN 1 ELSE 0 END) as first_count
        FROM availability a
        LEFT JOIN programs p ON a.source = p.source
        WHERE a.expired_at IS NULL
        GROUP BY a.source, p.program_name, p.airline_name, p.alliance, p.currency, p.iata_code
        ORDER BY total_flights DESC
    """
    rows = conn.execute(sql).fetchall()
    columns = ["source", "program_name", "airline_name", "alliance", "currency", "airline_iata",
               "total_flights", "routes", "earliest_date", "latest_date",
               "economy_count", "premium_economy_count", "business_count", "first_count"]
    return [dict(zip(columns, row)) for row in rows]


def get_route_availability(origin, destination, cabin="J", source=None):
    """Get all dates for a specific route with enrichment."""
    conn = get_conn()
    cabin_lower = cabin.lower()
    conditions = [
        "a.expired_at IS NULL",
        f"a.{cabin_lower}_available = true",
        "a.origin = ?",
        "a.destination = ?"
    ]
    params = [origin.upper(), destination.upper()]

    if source:
        conditions.append("a.source = ?")
        params.append(source.lower())

    where = " AND ".join(conditions)
    sql = f"""
        SELECT a.date, a.source, a.{cabin_lower}_mileage as mileage,
               a.{cabin_lower}_taxes as taxes, a.{cabin_lower}_seats as seats,
               a.direct, a.airlines, a.equipment,
               oa.name as origin_city, oa.country as origin_country,
               da.name as dest_city, da.country as dest_country,
               r.distance,
               COALESCE(pr.best_mileage, 0) as best_ever_mileage
        FROM availability a
        LEFT JOIN airports oa ON a.origin = oa.iata_code
        LEFT JOIN airports da ON a.destination = da.iata_code
        LEFT JOIN routes r ON a.origin = r.origin AND a.destination = r.destination AND a.source = r.source
        LEFT JOIN price_records pr ON a.origin = pr.origin AND a.destination = pr.destination
                                   AND a.source = pr.source AND pr.cabin = ?
        WHERE {where}
        ORDER BY a.date ASC, a.{cabin_lower}_mileage ASC
    """
    params.insert(0, cabin_lower)
    rows = conn.execute(sql, params).fetchall()
    columns = ["date", "source", "mileage", "taxes", "seats", "direct", "airlines", "equipment",
               "origin_city", "origin_country", "dest_city", "dest_country", "distance", "best_ever_mileage"]
    return [dict(zip(columns, row)) for row in rows]


def find_sweet_spots(cabin="J", limit=50):
    """Find best-value award redemptions across all programs with enrichment."""
    conn = get_conn()
    cabin_lower = cabin.lower()
    sql = f"""
        SELECT a.source, a.origin, a.destination,
               MIN(a.{cabin_lower}_mileage) as min_mileage,
               AVG(a.{cabin_lower}_mileage) as avg_mileage,
               MIN(a.{cabin_lower}_taxes) as min_taxes,
               COUNT(*) as availability_count,
               MIN(a.date) as first_date,
               MAX(a.date) as last_date,
               oa.name as origin_city, oa.country as origin_country,
               da.name as dest_city, da.country as dest_country,
               p.program_name, p.alliance,
               r.distance,
               COALESCE(pr.best_mileage, 0) as best_ever_mileage
        FROM availability a
        LEFT JOIN airports oa ON a.origin = oa.iata_code
        LEFT JOIN airports da ON a.destination = da.iata_code
        LEFT JOIN programs p ON a.source = p.source
        LEFT JOIN routes r ON a.origin = r.origin AND a.destination = r.destination AND a.source = r.source
        LEFT JOIN price_records pr ON a.origin = pr.origin AND a.destination = pr.destination
                                   AND a.source = pr.source AND pr.cabin = ?
        WHERE a.expired_at IS NULL AND a.{cabin_lower}_available = true
              AND a.{cabin_lower}_mileage > 0
        GROUP BY a.source, a.origin, a.destination, oa.name, oa.country, da.name, da.country,
                 p.program_name, p.alliance, r.distance, pr.best_mileage
        HAVING COUNT(*) >= 3
        ORDER BY MIN(a.{cabin_lower}_mileage) ASC
        LIMIT ?
    """
    params = [cabin_lower, limit]
    rows = conn.execute(sql, params).fetchall()
    columns = ["source", "origin", "destination", "min_mileage", "avg_mileage", "min_taxes",
               "availability_count", "first_date", "last_date",
               "origin_city", "origin_country", "dest_city", "dest_country",
               "program_name", "alliance", "distance", "best_ever_mileage"]
    return [dict(zip(columns, row)) for row in rows]


def get_program_details(program_slug):
    """Deep dive on a single program with metadata and transfer partners."""
    conn = get_conn()
    program_slug_lower = program_slug.lower()

    # Get program stats
    sql = """
        SELECT
            COUNT(*) as total_availability,
            COUNT(DISTINCT origin || '-' || destination) as unique_routes,
            COUNT(DISTINCT origin) as origin_airports,
            COUNT(DISTINCT destination) as destination_airports,
            MIN(date) as earliest_date,
            MAX(date) as latest_date,
            AVG(CASE WHEN j_available AND j_mileage > 0 THEN j_mileage END) as avg_business_miles,
            AVG(CASE WHEN y_available AND y_mileage > 0 THEN y_mileage END) as avg_economy_miles,
            MIN(CASE WHEN j_available AND j_mileage > 0 THEN j_mileage END) as min_business_miles,
            MIN(CASE WHEN y_available AND y_mileage > 0 THEN y_mileage END) as min_economy_miles
        FROM availability
        WHERE expired_at IS NULL AND source = ?
    """
    row = conn.execute(sql, [program_slug_lower]).fetchone()
    if not row:
        return None

    stats = dict(zip(["total_availability", "unique_routes", "origin_airports", "destination_airports",
                      "earliest_date", "latest_date", "avg_business_miles", "avg_economy_miles",
                      "min_business_miles", "min_economy_miles"], row))

    # Get program metadata
    program_sql = """
        SELECT program_name, airline_name, alliance, currency, iata_code, active, last_ingested
        FROM programs
        WHERE source = ?
    """
    prog_row = conn.execute(program_sql, [program_slug_lower]).fetchone()
    if prog_row:
        stats["program_name"] = prog_row[0]
        stats["airline_name"] = prog_row[1]
        stats["alliance"] = prog_row[2]
        stats["currency"] = prog_row[3]
        stats["iata_code"] = prog_row[4]
        stats["active"] = prog_row[5]
        stats["last_ingested"] = prog_row[6]

    # Get transfer partners
    transfer_sql = """
        SELECT bank, ratio, current_bonus, bonus_percent, bonus_expires, transfer_speed
        FROM transfer_cache
        WHERE program = ?
        ORDER BY ratio DESC
    """
    transfers = conn.execute(transfer_sql, [program_slug_lower]).fetchall()
    stats["transfer_partners"] = [
        {
            "bank": t[0],
            "ratio": t[1],
            "current_bonus": t[2],
            "bonus_percent": t[3],
            "bonus_expires": t[4],
            "transfer_speed": t[5]
        }
        for t in transfers
    ]

    return stats


def get_market_stats():
    """Aggregate stats across entire database."""
    conn = get_conn()
    sql = """
        SELECT
            COUNT(*) as total_records,
            COUNT(DISTINCT source) as programs,
            COUNT(DISTINCT origin) as origin_airports,
            COUNT(DISTINCT destination) as destination_airports,
            COUNT(DISTINCT origin || '-' || destination) as unique_routes,
            MIN(date) as earliest_date,
            MAX(date) as latest_date,
            SUM(CASE WHEN j_available THEN 1 ELSE 0 END) as business_availability,
            SUM(CASE WHEN f_available THEN 1 ELSE 0 END) as first_availability,
            SUM(CASE WHEN y_available THEN 1 ELSE 0 END) as economy_availability
        FROM availability
        WHERE expired_at IS NULL
    """
    row = conn.execute(sql).fetchone()
    stats = dict(zip(["total_records", "programs", "origin_airports", "destination_airports",
                      "unique_routes", "earliest_date", "latest_date", "business_availability",
                      "first_availability", "economy_availability"], row))

    # Add counts from reference tables
    airports_count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
    programs_count = conn.execute("SELECT COUNT(*) FROM programs WHERE active = true").fetchone()[0]
    transfer_partners_count = conn.execute("SELECT COUNT(DISTINCT bank) FROM transfer_cache").fetchone()[0]

    stats["total_airports"] = airports_count
    stats["active_programs"] = programs_count
    stats["transfer_banks"] = transfer_partners_count

    return stats


def get_airport_info(iata_code):
    """Look up full airport details."""
    conn = get_conn()
    row = conn.execute(
        """SELECT iata_code, name, city, country, country_code, continent, region,
                  latitude, longitude, timezone, airport_type, programs_serving
           FROM airports WHERE iata_code = ?""",
        [iata_code.upper()]
    ).fetchone()
    if not row:
        return None
    return {
        "iata_code": row[0],
        "name": row[1],
        "city": row[2],
        "country": row[3],
        "country_code": row[4],
        "continent": row[5],
        "region": row[6],
        "latitude": row[7],
        "longitude": row[8],
        "timezone": row[9],
        "airport_type": row[10],
        "programs_serving": row[11]
    }


def get_transfer_partners(program_slug):
    """Get all banks that transfer to a program."""
    conn = get_conn()
    sql = """
        SELECT bank, ratio, current_bonus, bonus_percent, bonus_expires, transfer_speed
        FROM transfer_cache
        WHERE program = ?
        ORDER BY ratio DESC
    """
    rows = conn.execute(sql, [program_slug.lower()]).fetchall()
    columns = ["bank", "ratio", "current_bonus", "bonus_percent", "bonus_expires", "transfer_speed"]
    return [dict(zip(columns, row)) for row in rows]


def get_price_history(origin, destination, source, cabin):
    """Get historical price records for a route."""
    conn = get_conn()
    row = conn.execute(
        """SELECT best_mileage, best_taxes, best_date, best_flight, best_equipment, best_direct,
                  first_seen, last_seen, times_seen, beaten_count
           FROM price_records
           WHERE origin = ? AND destination = ? AND source = ? AND cabin = ?""",
        [origin.upper(), destination.upper(), source.lower(), cabin.upper()]
    ).fetchone()
    if not row:
        return None
    return {
        "best_mileage": row[0],
        "best_taxes": row[1],
        "best_date": row[2],
        "best_flight": row[3],
        "best_equipment": row[4],
        "best_direct": row[5],
        "first_seen": row[6],
        "last_seen": row[7],
        "times_seen": row[8],
        "beaten_count": row[9]
    }
