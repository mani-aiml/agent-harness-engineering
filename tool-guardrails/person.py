"""The last layer, a person: a queued ticket with the call, the reason and the records.

`python person.py` lists the queue. `python person.py approve <n>` runs ticket n through the refund
credential, so a person's yes still can't go past the sandbox's limits.
"""

import json
import sys
from pathlib import Path

from calls import PERSON, Call, Verdict, facts
from meter import Meter
from tools import OverLimit, call_tool

QUEUE = Path(__file__).parent / "runs" / "queue.jsonl"


def tickets() -> list[dict]:
    return [json.loads(line) for line in QUEUE.read_text().splitlines()] if QUEUE.exists() else []


def queue(call: Call, reason: str, meter: Meter) -> Verdict:
    """Open a ticket and tell the agent the call is waiting on a person."""
    number = len(tickets()) + 1
    # Decision: the ticket carries the records the guard fetched, so the person isn't reading cold.
    ticket = {"ticket": number, "call": str(call), "name": call.name, "args": call.args,
              "customer": call.customer, "request": call.request, "why": reason, "records": facts(call)}
    QUEUE.parent.mkdir(exist_ok=True)
    with QUEUE.open("a") as out:
        out.write(json.dumps(ticket) + "\n")
    meter.say(f"ticket {number} for a person: {call} ({reason})")
    return Verdict(PERSON, "person", reason)


def approve(number: int) -> str:
    ticket = next(t for t in tickets() if t["ticket"] == number)
    try:
        return call_tool(ticket["name"], ticket["args"], ticket["customer"])
    except OverLimit as refused:
        return f"The credential refused ticket {number}: {refused}"


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "approve":
        print(approve(int(sys.argv[2])))
    else:
        for t in tickets():
            print(f"{t['ticket']:>3}  {t['call']:<50} {t['why']}")
