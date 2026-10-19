"""Layer 1, rules: checks in code that settle the obvious calls, with no model and no cost.

Decision: a rule can only stop a call or let it go on to the next layer. It never approves one,
because a rule can't see whether the customer really asked for it.
"""

import re

from calls import STOP, Call, Verdict
from tools import DATA, owner_of

FORMATS = {"order_id": r"O-\d+", "customer_id": r"C-\d+", "email": r"[^@\s]+@[^@\s]+\.[a-z]{2,}"}
TABLES = {"order_id": "orders", "customer_id": "customers"}


def bad_arguments(call: Call) -> str | None:
    for arg, value in call.args.items():
        if arg in FORMATS and not re.fullmatch(FORMATS[arg], str(value)):
            return f"{arg} {value!r} isn't a valid {arg.replace('_', ' ')}"
        if arg in TABLES and value not in DATA[TABLES[arg]]:
            return f"there's no {arg.replace('_', ' ')} {value}"
    if "amount" in call.args and not (isinstance(call.args["amount"], (int, float)) and call.args["amount"] > 0):
        return f"a refund amount must be a positive number, not {call.args['amount']!r}"
    if "address" in call.args and not re.search(r"\d.*,", call.args["address"]):
        return f"{call.args['address']!r} doesn't look like a full address"
    return None


def not_this_customer(call: Call) -> str | None:
    owner = owner_of(call.args)
    return None if owner == call.customer else f"it touches {owner}'s account, and this is {call.customer}'s conversation"


def more_than_was_paid(call: Call) -> str | None:
    if call.name != "issue_refund":
        return None
    invoice = DATA["invoices"][call.args["order_id"]]
    left = sum(charge["amount"] for charge in invoice["charges"]) - invoice["refunded"]
    return f"${call.args['amount']:,.2f} is more than the ${left:,.2f} charged and not yet refunded" if call.args["amount"] > left else None


def too_late(call: Call) -> str | None:
    if "order_id" not in call.args:
        return None
    status = DATA["orders"][call.args["order_id"]]["status"]
    if call.name == "cancel_order" and status in {"shipped", "delivered"}:
        return f"the order is already {status}, so it can't be cancelled"
    if call.name in {"update_address", "hold_shipment"} and status == "delivered":
        return "the order is already delivered"
    return None


# Decision: bad_arguments runs first, so every later rule can trust the ids it reads.
RULES = [bad_arguments, not_this_customer, more_than_was_paid, too_late]


def check(call: Call) -> Verdict | None:
    """The first rule that fails stops the call. None means the rules let it go on."""
    for rule in RULES:
        reason = rule(call)
        if reason:
            return Verdict(STOP, "rules", reason)
    return None
