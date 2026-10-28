# Observability: trace every step your agent takes

The code behind the video **AI Agent Observability: Read the Trace with Langfuse** (Agent Harness Engineering).
A support agent with a guard on its writes, traced with seven lines, so every model call, tool call and guard
decision shows up in [Langfuse](https://langfuse.com) as one trace per customer request.

## The seven lines

| # | where | line | what it gives you |
|---|---|---|---|
| 1 | `loop.py` | `anthropic.Anthropic(open_telemetry={"traces": {"content_mode": "content"}})` | a span for every model call, with what the model was sent and said back |
| 2 | `loop.py` | `@observe(as_type="agent")` on `run_agent` | one trace per customer request, every step nested under it |
| 3 | `loop.py` | `@observe(as_type="tool")` on `run_tool` | what the model asked a tool for, and what came back |
| 4 | `loop.py` | `get_client().update_current_span(name=block.name)` | tool spans named `get_order`, `hold_shipment`, not `run_tool` |
| 5 | `guard.py` | `@observe(as_type="guardrail")` on `guard` | which layer settled the call, and why |
| 6 | `jev_guard.py` | `@observe(as_type="guardrail", name="jev")` on `ask` | the decision model's choice and its confidence |
| 7 | `loop.py` | `with propagate_attributes(user_id=customer):` | every span tagged with the customer, so you can filter by user |

Plus their imports. Every design choice is marked in the code with a `# Decision:` comment.

`content_mode: "content"` records your prompts and responses, which is your customers' data: in production,
mask it or limit what you keep.

## Bring your own data

The demo's records and labelled calls aren't published. Add your own two files next to the code.

**`data.json`**, the system of record the tools read and the guard fetches from:

```json
{
  "today": "2026-10-03",
  "customers": {"C-1": {"name": "...", "region": "US", "tier": "starter", "order_ids": ["O-1"], "email": "...", "address": "..."}},
  "orders": {"O-1": {"customer_id": "C-1", "status": "delivered", "placed": "2026-08-20", "skus": ["SKU-1"], "total": 249.0}},
  "shipments": {"O-1": {"carrier": "...", "status": "delivered", "last_scan": "2026-08-24 Austin", "eta": "2026-08-24"}},
  "invoices": {"O-1": {"amount": 249.0, "paid": true, "charges": [{"date": "2026-08-20", "amount": 249.0}], "refunded": 0.0}},
  "inventory": {"SKU-1": {"name": "...", "in_stock": 14, "restock": null}},
  "warranties": {"SKU-1": {"months": 24, "covers": "..."}},
  "tickets": {"C-1": [{"id": "T-1", "opened": "2026-09-12", "subject": "...", "status": "open"}]},
  "refund_policies": {"US": "Full refund within 30 days of delivery. Duplicate charges are refunded in 3 business days."}
}
```

Order status is one of `processing`, `backordered`, `shipped` or `delivered`. Customer and order ids
must look like `C-<digits>` and `O-<digits>`, because the rules check the format.

Without `data.json` the tests skip and the demo stops with a pointer to this section.

## Run it

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # then fill it in
```

1. Langfuse: self-host it (see Langfuse's self-hosting docs) or use Langfuse Cloud. The code is the same; only
   the address and the two keys in `.env` change.
2. The agent's model: `ollama pull qwen3:4b` and keep `ANTHROPIC_BASE_URL` pointing at Ollama, or point the client
   at Claude (see `.env.example`). If your shell already exports `ANTHROPIC_BASE_URL`, it wins over `.env`, so pass
   it on the command line.
3. `python loop.py C-48 "Where's my order O-1084?"`, then open the trace in Langfuse.

Offline tests, no model calls: `LANGFUSE_TRACING_ENABLED=false pytest test_guard.py`.

The numbers in the video come from my own runs (15 Oct 2026, Qwen 3 4B on a laptop, made-up support data).
Yours will look different, so test on your own agent.
