"""Side probe from 27 Sep 2026, kept so the numbers in the README can be rerun. Run from the folder above."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import tools, loop, tool_returns
from meter import Meter
tools.carrier_down = True
task = "Where is order O-1042 right now, and when will it arrive?"
for name, arm in {"raw traceback": loop.run_agent, "clear return": tool_returns.with_clear_returns}.items():
    calls, toks, shipment_asks = [], [], []
    for _ in range(10):
        m = Meter(loop.MODEL, quiet=True)
        arm(task, m)
        calls.append(m.claude_calls); toks.append(m.input_tokens)
    print(f"{name:14} calls {calls}  median tokens {sorted(toks)[5]}", flush=True)
