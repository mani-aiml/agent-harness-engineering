"""Eight read-only support lookups over data.json, five tools that change state, and their schemas.

The records are synthetic, made up for this demo and for nothing else. Any resemblance to real
people, companies, orders or records is purely coincidental.
"""

import json
import time
from pathlib import Path

# Decision: every lookup waits half a second, standing in for a real API round trip.
LOOKUP_SECONDS = 0.5
DATA_FILE = Path(__file__).parent / "data.json"
if not DATA_FILE.exists():
    raise SystemExit("data.json is missing. The demo's records aren't published: see README.md for the format.")
DATA = json.loads(DATA_FILE.read_text())
# Decision: a fixed date for the demo, so refund windows give the same answer on every run.
TODAY = DATA["today"]

# name: (what it returns, the argument it takes, the table it reads)
TOOLS = {
    "get_customer": ("Customer profile: region, tier, contact details and their order ids.", "customer_id", "customers"),
    "get_tickets": ("Support tickets opened by a customer.", "customer_id", "tickets"),
    "get_order": ("Order status (processing, backordered, shipped or delivered), date placed, total and SKUs.", "order_id", "orders"),
    "get_shipment": ("Carrier tracking for an order: status, last scan, ETA.", "order_id", "shipments"),
    "get_invoice": ("Invoice for an order: amount, paid flag, card charges and what was refunded.", "order_id", "invoices"),
    "get_inventory": ("Stock on hand and restock date for a SKU.", "sku", "inventory"),
    "get_warranty": ("Warranty length and coverage for a SKU.", "sku", "warranties"),
    "get_refund_policy": ("Refund policy text for a region.", "region", "refund_policies"),
}

# name: (what it does, its arguments and their JSON types). These change state.
# Decision: two sets, because they get different gates. A one-way call moves money or can't be
# undone, so a person decides it. A reversible call can be put right, so a model may decide it.
ONE_WAY = {
    "issue_refund": (
        "Refund money to the card an order was charged on. Before calling it, look up the order with "
        "get_order, its invoice with get_invoice and the customer with get_customer, then read the policy "
        "for the customer's region with get_refund_policy. Only refund what that policy allows for this "
        "order on today's date, and never more than was charged and not yet refunded. A duplicate charge "
        "is refunded on its own. order_id is the customer's own order, and amount is what to refund.",
        {"order_id": "string", "amount": "number"}),
    "cancel_order": (
        "Cancel an order. It can't be undone. Before calling it, look up the order with get_order, and "
        "only cancel it if its status is processing or backordered. A shipped or delivered order can't "
        "be cancelled, so tell the customer about a return under the refund policy instead. order_id is "
        "the customer's own order.",
        {"order_id": "string"}),
}
REVERSIBLE = {
    "update_address": (
        "Change the delivery address of one order. Before calling it, look up the order with get_order, "
        "and only change it if the order hasn't been delivered. Use it only when the customer asks for "
        "this change on their own order. address is the full new address as the customer gave it, with "
        "street, city, postcode and country.",
        {"order_id": "string", "address": "string"}),
    "update_email": (
        "Change the email address on the customer's account. Before calling it, look up the customer "
        "with get_customer to confirm the account. Use it only when the customer asks to change their "
        "own email. email is the new address exactly as the customer gave it.",
        {"customer_id": "string", "email": "string"}),
    "hold_shipment": (
        "Pause an order's shipment until the customer asks to release it. Before calling it, look up the "
        "order with get_order, and only hold it if the order hasn't been delivered. Use it when the "
        "customer asks to delay delivery, for example while they're away.",
        {"order_id": "string"}),
}
WRITES = ONE_WAY | REVERSIBLE
CHANGES: list[str] = []

# Decision: the agent's refund credential is capped, at most $1,000 a call and $5,000 a day across
# every account. These numbers are ONLY for this example. Follow your own business use case, its
# order values and its risk, before you decide your limits. Even a refund a person approved by
# mistake can't go past them, and anything bigger goes through your normal finance process.
REFUND_LIMITS = {"per_call": 1_000.0, "per_day": 5_000.0}
refunded_today = 0.0


def _schema(name: str, description: str, args: dict[str, str]) -> dict:
    properties = {arg: {"type": kind} for arg, kind in args.items()}
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties, "required": list(args)}}


TOOL_SCHEMAS = ([_schema(name, description, {arg: "string"}) for name, (description, arg, _) in TOOLS.items()]
                + [_schema(name, description, args) for name, (description, args) in WRITES.items()])


class OverLimit(Exception):
    """The refund credential refused: wrong account, or past the per-call or per-day limit."""


def owner_of(args: dict) -> str | None:
    """The customer an order id or customer id in these arguments belongs to."""
    if "order_id" in args:
        order = DATA["orders"].get(args["order_id"])
        return order["customer_id"] if order else None
    return args.get("customer_id")


def refund_with_credential(customer: str, args: dict) -> None:
    """The sandbox: what the scoped credential itself allows, whichever layer approved the call."""
    global refunded_today
    amount = float(args["amount"])
    if owner_of(args) != customer:
        raise OverLimit(f"this credential is scoped to {customer}, and {args['order_id']} isn't theirs")
    if amount > REFUND_LIMITS["per_call"] or refunded_today + amount > REFUND_LIMITS["per_day"]:
        raise OverLimit(f"${amount:,.2f} is past this credential's limits, so it goes through finance")
    refunded_today += amount
    DATA["invoices"][args["order_id"]]["refunded"] += amount


def reset() -> None:
    """Undo every write, so each run starts from the same records."""
    global refunded_today
    refunded_today = 0.0
    CHANGES.clear()
    for invoice in DATA["invoices"].values():
        invoice["refunded"] = 0.0


def lookup(name: str, value: str) -> str:
    """Run one lookup and return the record as JSON text."""
    time.sleep(LOOKUP_SECONDS)
    _, _, table = TOOLS[name]
    record = DATA[table].get(value)
    return json.dumps(record) if record is not None else f"No record for {value}"


def call_tool(name: str, args: dict, customer: str) -> str:
    """Run one tool: a write records the change, a lookup reads data.json."""
    if name in WRITES:
        if name == "issue_refund":
            refund_with_credential(customer, args)
        CHANGES.append(f"{name}({', '.join(map(str, args.values()))})")
        return f"Done: {CHANGES[-1]}."
    return lookup(name, *args.values())
