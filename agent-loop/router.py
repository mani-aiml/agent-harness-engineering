"""Change 2, a router in front of the loop.

One cheap decision picks the path before any Claude call: look up this customer's records,
answer from policy, or hand an action to a person. When the router is unsure, the plain loop runs.
"""

import sys
import time

from typesafe_sdk import Choice

from jev_fetches import jev, jev_fetches
from loop import MAX_TOKENS, MODEL, client, run_agent, text_of
from meter import Meter, compare
from tools import DATA

ROUTES = {
    "lookup": "Needs this customer's own records: orders, shipments, invoices, tickets, stock or warranty.",
    "policy": "A general question our refund policies answer, with no customer records needed.",
    "human": "Asks us to take an action, like issuing a refund, cancelling or changing an order.",
}
# Decision: below 0.8 the router's shortcut isn't trusted, and the task gets the full loop.
ROUTE_AT = 0.8
TASKS = [
    "Customer C-17 says their gateway order never arrived. What happened to it?",
    "When will order O-1090 ship? Tell me what it is waiting on.",
    "Customer C-23 says they were charged twice for order O-1051. Is that true?",
    "What is our refund policy for customers in the UK?",
    "Do EU customers get a refund if an order is stuck in transit?",
    "Please refund order O-1051 to the card it was charged on.",
    "Cancel order O-1077, the customer changed their mind.",
]


def route_with_jev(task: str, meter: Meter) -> tuple[str, float]:
    # Decision: Jev returns a typed choice and a probability in one call, and writes nothing.
    response = jev.system_one(state=task, questions={"route": Choice(
        instructions="Which path should this support request take?", criteria=ROUTES)})
    answer = response.choices["route"]
    meter.jev(response, f"route: {answer.choice} (confidence {answer.confidence:.2f})")
    return answer.choice, answer.confidence


def route_with_claude(task: str, meter: Meter) -> tuple[str, float]:
    options = "\n".join(f"{name}: {description}" for name, description in ROUTES.items())
    reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": task}],
                                   system=f"Pick the path for this support request. Reply with one word.\n{options}")
    meter.claude(reply)
    # Claude gives a label as text. There is no probability to set a bar on, so it counts as sure.
    return text_of(reply).strip().lower(), 1.0


def answer_from_policy(task: str, meter: Meter) -> str:
    # Decision: the policies are short, so they go in the prompt. One call, no tools.
    policies = "\n".join(f"{region}: {text}" for region, text in DATA["refund_policies"].items())
    reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": task}],
                                   system=f"Answer from these refund policies in two sentences.\n{policies}")
    meter.claude(reply)
    return text_of(reply)


def hand_to_person(task: str, meter: Meter) -> str:
    # Decision: actions that change money or orders go to a person, never to a model.
    meter.say("queued for a person to approve")
    return "Queued for a person to approve."


PATHS = {"lookup": jev_fetches, "policy": answer_from_policy, "human": hand_to_person}


def routed(task: str, meter: Meter, router=route_with_jev) -> str:
    route, confidence = router(task, meter)
    if confidence < ROUTE_AT or route not in PATHS:
        meter.say("not sure, so the plain loop runs")
        return run_agent(task, meter)
    return PATHS[route](task, meter)


def who_routes() -> None:
    """The same decision made by Jev and by Claude, on every task."""
    routers = {"Jev": route_with_jev, "Claude": route_with_claude}
    meters = {name: Meter(MODEL, quiet=True) for name in routers}
    seconds = dict.fromkeys(routers, 0.0)
    print(f"{'task':<70}{'Jev':>22}{'Claude':>16}")
    for task in TASKS:
        picks = []
        for name, router in routers.items():
            started = time.perf_counter()
            route, confidence = router(task, meters[name])
            seconds[name] += time.perf_counter() - started
            picks.append(f"{route} ({confidence:.2f})" if name == "Jev" else route)
        print(f"{task[:68]:<70}{picks[0]:>22}{picks[1]:>16}")
    for name, meter in meters.items():
        print(f"{name}: {seconds[name] / len(TASKS):.2f} s and ${meter.usd / len(TASKS):.6f} per decision")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        compare(sys.argv[1], MODEL, {"before: the plain loop": run_agent, "after: routed": routed},
                int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        who_routes()
