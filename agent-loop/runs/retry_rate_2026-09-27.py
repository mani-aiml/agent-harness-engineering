"""Side probe from 27 Sep 2026, kept so the numbers in the README can be rerun. Run from the folder above.

Carrier timeout on, ten runs per arm: Claude calls, input tokens and shipment lookups per run.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import loop  # noqa: E402
import tool_returns  # noqa: E402
import tools  # noqa: E402
from meter import Meter  # noqa: E402

RUNS = 10
TASK = "Where is order O-1042 right now, and when will it arrive?"
tools.carrier_down = True
shipment_asks = 0
real_lookup = tools.lookup


def counting_lookup(name: str, value: str) -> str:
    global shipment_asks
    shipment_asks += name == "get_shipment"
    return real_lookup(name, value)


loop.lookup = counting_lookup
for label, arm in {"raw traceback": loop.run_agent, "clear return": tool_returns.with_clear_returns}.items():
    calls, tokens, shipments = [], [], []
    for _ in range(RUNS):
        shipment_asks = 0
        meter = Meter(loop.MODEL, quiet=True)
        arm(TASK, meter)
        calls.append(meter.claude_calls)
        tokens.append(meter.input_tokens)
        shipments.append(shipment_asks)
    print(f"{label}: calls {calls}, shipment lookups {shipments}")
    print(f"{label}: input tokens {tokens}, median {statistics.median(tokens):,.0f}", flush=True)
