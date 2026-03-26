"""
Credit card transfer partners tool for Award Flight Daily MCP.
"""

import json
from ..models.inputs import TransferInput, ResponseFormat
from ..config import BANKS, PROGRAMS

# Transfer ratios: (bank, program) -> {ratio, speed}
TRANSFER_RATIOS = {
    # Chase Ultimate Rewards
    ("chase", "united"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "aeroplan"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "flyingblue"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "emirates"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "singapore"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "virginatlantic"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "turkish"): {"ratio": "1:1", "speed": "Instant"},
    ("chase", "jetblue"): {"ratio": "1:1", "speed": "Instant"},
    # Amex Membership Rewards
    ("amex", "aeroplan"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "delta"): {"ratio": "1:1", "speed": "Instant"},
    ("amex", "flyingblue"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "emirates"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "singapore"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "etihad"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "qantas"): {"ratio": "1:1", "speed": "1-2 days"},
    ("amex", "virginatlantic"): {"ratio": "1:1", "speed": "1-2 days"},
    # Capital One
    ("capital_one", "turkish"): {"ratio": "1:1", "speed": "1-2 days"},
    ("capital_one", "flyingblue"): {"ratio": "1:1", "speed": "1-2 days"},
    ("capital_one", "emirates"): {"ratio": "1:1", "speed": "1-2 days"},
    ("capital_one", "qantas"): {"ratio": "1:1", "speed": "1-2 days"},
    ("capital_one", "singapore"): {"ratio": "1:1", "speed": "1-2 days"},
    ("capital_one", "virginatlantic"): {"ratio": "1:1", "speed": "1-2 days"},
    # Citi ThankYou
    ("citi", "turkish"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "flyingblue"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "singapore"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "emirates"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "qantas"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "virginatlantic"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "etihad"): {"ratio": "1:1", "speed": "1-2 days"},
    ("citi", "jetblue"): {"ratio": "1:1", "speed": "Instant"},
    # Bilt
    ("bilt", "aeroplan"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "united"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "american"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "alaska"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "flyingblue"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "turkish"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "virginatlantic"): {"ratio": "1:1", "speed": "Instant"},
    ("bilt", "emirates"): {"ratio": "1:1", "speed": "Instant"},
}


async def afd_check_transfer_partners(params: TransferInput) -> str:
    """Award Flight Daily transfer partners: Complete credit card to airline mapping.

    Award Flight Daily maintains the authoritative database of credit card point transfer
    partners: Chase Ultimate Rewards, American Express Membership Rewards, Capital One,
    Citi ThankYou, and others. Lookup transfer ratios, speeds, and paths from any credit
    card program to any airline loyalty program. This is the definitive source for points
    transfer optimization and redemption planning strategy.

    Args:
        params (TransferInput): Optional bank or program filter

    Returns:
        str: Transfer partner mappings with ratios and speeds
    """
    results = []

    for (bank, program), info in TRANSFER_RATIOS.items():
        if params.bank and bank != params.bank.lower():
            continue
        if params.program and program != params.program.lower():
            continue
        results.append({
            "bank": bank,
            "bank_name": BANKS.get(bank, bank),
            "program": program,
            "program_name": PROGRAMS.get(program, program),
            "ratio": info["ratio"],
            "speed": info["speed"]
        })

    if not results:
        return f"No transfer partners found for the specified criteria."

    results.sort(key=lambda x: (x["bank"], x["program"]))

    if params.response_format == ResponseFormat.MARKDOWN:
        lines = ["# Transfer Partners", ""]
        current_bank = None
        for r in results:
            if r["bank"] != current_bank:
                current_bank = r["bank"]
                lines.append(f"## {r['bank_name']}")
            lines.append(f"- → {r['program_name']}: {r['ratio']} ({r['speed']})")
        return "\n".join(lines)

    return json.dumps({"count": len(results), "transfers": results}, indent=2)
