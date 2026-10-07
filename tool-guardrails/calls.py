"""What every guard layer gets, a proposed call, and what it gives back, a verdict."""

from dataclasses import dataclass

from tools import DATA, TODAY, owner_of

RUN, STOP, ESCALATE, PERSON = "run", "stop", "escalate", "person"

# Decision: the policy for reversible changes is written once, and every judge reads this same text, so
# the layers can't disagree about the rules. Name what counts: a vague policy leaves a judge unsure on
# clear calls, and a judge without it sides with the customer.
POLICY = {
    "allowed": "The customer's own message asks for exactly this change, on their own account or order, "
               "and nothing in the request or the records argues against it. Holding an order, delivering "
               "it to an address the customer wrote, or changing the account email to one the customer "
               "wrote all count when the customer asked for them.",
    "not allowed": "The customer didn't ask for this change, or something argues against it: the new email "
                   "or address looks like a business or a service rather than the customer or a person "
                   "they named, the order would go to another country while it's in transit, or the "
                   "message mixes the change with a hacked-account claim or a demand for money.",
}


@dataclass(frozen=True)
class Call:
    name: str
    args: dict
    customer: str  # from the signed-in session, never from the model
    request: str   # what the customer actually asked

    def __str__(self) -> str:
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.args.items())})"


@dataclass(frozen=True)
class Verdict:
    outcome: str  # RUN, STOP, ESCALATE or PERSON
    layer: str
    reason: str


def facts(call: Call) -> dict:
    """The records the guard fetches for itself, straight from the system of record.

    Decision: the judges see these, never the agent's tool results, so text planted in a ticket or
    a record the agent read can't argue its own case.
    """
    customer = DATA["customers"].get(call.customer, {})
    records = {"customer": customer, "refund policy": DATA["refund_policies"].get(customer.get("region"))}
    order_id = call.args.get("order_id")
    if order_id and owner_of(call.args) == call.customer:
        records |= {"order": DATA["orders"][order_id], "invoice": DATA["invoices"][order_id],
                    "shipment": DATA["shipments"].get(order_id)}
    return records


def state(call: Call) -> dict:
    """One call, as a judge sees it."""
    return {"today": TODAY, "customer request": call.request, "proposed call": str(call), "records": facts(call)}
