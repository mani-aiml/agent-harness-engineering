"""Side probe from 27 Sep 2026, kept so the numbers in the README can be rerun. Run from the folder above."""
import sys, statistics, traceback
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import tools, loop
from meter import Meter
tools.LOOKUP_SECONDS = 0

class NotFound(KeyError): pass
class Timeout(TimeoutError): pass

def db_get(table, key):
    if key not in tools.DATA[table]:
        raise NotFound(key)
    return tools.DATA[table][key]

def raw_lookup(name, value, mode):
    _, _, table = tools.TOOLS[name]
    if mode == "timeout" and name == "get_shipment":
        raise Timeout("HTTPSConnectionPool(host='tracking.carrier.example', port=443): Read timed out. (read timeout=10)")
    import json
    return json.dumps(db_get(table, value))

def clear(name, value, mode):
    _, arg, table = tools.TOOLS[name]
    if mode == "timeout" and name == "get_shipment":
        return "Carrier tracking timed out and is down right now; retrying won't help. Answer without tracking and say it's unavailable.", True
    if value not in tools.DATA[table]:
        hint = {"order_id": "Order ids look like O-1042.", "customer_id": "Customer ids look like C-17.", "sku": "SKUs look like SKU-301."}.get(arg, "")
        known = ", ".join(sorted(tools.DATA[table]))
        return f"No {arg} {value!r}. {hint} Known ids: {known}.", True
    import json
    return json.dumps(tools.DATA[table][value]), False

def make_runner(mode, style):
    def run_tool(block, meter):
        name, value = block.name, next(iter(block.input.values()))
        meter.lookup(name, value)
        if style == "raw":
            try:
                out, err = raw_lookup(name, value, mode), False
            except Exception:
                out, err = traceback.format_exc(), False
        else:
            out, err = clear(name, value, mode)
        r = {"type": "tool_result", "tool_use_id": block.id, "content": out}
        if err: r["is_error"] = True
        return r
    return run_tool

CASES = {
    "timeout": "Where is order O-1042 right now, and when will it arrive?",
    "format": "Where is order 1042 right now?",
    "typo": "Customer C-17 is asking about order O-1024. Where is it?",
}
for mode, task in CASES.items():
    for style in ("raw", "clear"):
        calls, toks = [], []
        for _ in range(3):
            m = Meter(loop.MODEL, quiet=True)
            try:
                loop.run_agent(task, m, run_tool=make_runner(mode, style))
            except RuntimeError: pass
            calls.append(m.claude_calls); toks.append(m.input_tokens)
        print(f"{mode:8} {style:6} calls {calls} tokens {toks}", flush=True)
