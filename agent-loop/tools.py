"""Eight read-only support lookups over data.json, and the schemas Claude sees for them.

The records are synthetic, made up for this demo and for nothing else. Any resemblance to real
people, companies, orders or records is purely coincidental.
"""

import json
import re
import time
from pathlib import Path

# Decision: every lookup waits half a second, standing in for a real API round trip.
LOOKUP_SECONDS = 0.5
DATA = json.loads((Path(__file__).parent / "data.json").read_text())
REGIONS = ["US", "EU", "UK", "IN"]
ID_PATTERNS = {"customer_id": r"C-\d+", "order_id": r"O-\d+", "sku": r"SKU-\d+"}

# name: (what it returns, the argument it takes, the table it reads)
TOOLS = {
    "get_customer": ("Customer profile: region, tier and their order ids.", "customer_id", "customers"),
    "get_tickets": ("Support tickets opened by a customer.", "customer_id", "tickets"),
    "get_order": ("Order status, date, total and the SKUs in it.", "order_id", "orders"),
    "get_shipment": ("Carrier tracking for an order: status, last scan, ETA.", "order_id", "shipments"),
    "get_invoice": ("Invoice for an order: amount, paid flag and card charges.", "order_id", "invoices"),
    "get_inventory": ("Stock on hand and restock date for a SKU.", "sku", "inventory"),
    "get_warranty": ("Warranty length and coverage for a SKU.", "sku", "warranties"),
    "get_refund_policy": ("Refund policy text for a region.", "region", "refund_policies"),
}

TOOL_SCHEMAS = [
    {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": {arg: {"type": "string"}}, "required": [arg]},
    }
    for name, (description, arg, _) in TOOLS.items()
]

# Decision: the carrier outage is off by default, so only the tool-returns demo meets it.
carrier_down = False


class CarrierTimeout(TimeoutError):
    """What an HTTP client raises when the carrier's tracking API stops answering."""


def _call_carrier_api(order_id: str) -> None:
    if carrier_down:
        raise CarrierTimeout("HTTPSConnectionPool(host='tracking.carrier.example', port=443): "
                             f"Read timed out on /v2/shipments/{order_id}. (read timeout=10)")


def lookup(name: str, value: str) -> str:
    """Run one lookup and return the record as JSON text."""
    time.sleep(LOOKUP_SECONDS)
    _, _, table = TOOLS[name]
    if name == "get_shipment":
        _call_carrier_api(value)
    record = DATA[table].get(value)
    return json.dumps(record) if record is not None else f"No record for {value}"


def candidate_lookups(text: str) -> list[tuple[str, str]]:
    """Every (tool, value) pair the ids in `text` make possible, plus the policy for each region."""
    values = {arg: sorted(set(re.findall(pattern, text))) for arg, pattern in ID_PATTERNS.items()}
    values["region"] = REGIONS
    return [(name, value) for name, (_, arg, _) in TOOLS.items() for value in values[arg]]
