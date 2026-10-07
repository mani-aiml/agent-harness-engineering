# Tool guardrails: who decides whether a call runs

The code behind the video [Don't Trust the Prompt: Guardrail Your Agent's Tool Calls](https://youtu.be/zddpPndkWc8).
Once your agent can issue a refund or cancel an order, something has to decide whether that call
actually runs. Here, every tool call that changes something goes through a guard in the dispatch,
and the cheapest check that can settle the call goes first:

1. **Rules** check every write in code. They only stop a call or let it go on, and never approve one.
2. **Refunds and cancels** (`issue_refund`, `cancel_order`, which move money or can't be undone) then
   go to **a person**, at any amount.
3. **Reversible writes** (`update_address`, `update_email`, `hold_shipment`) go to **Jev**, a decision
   model from TypeSafe AI. Jev lets the call run, sends it to a person when it's very sure the call
   shouldn't run, or sends it to **Sonnet**, which allows it, denies it, or sends it to a person.
4. **The sandbox** caps what the agent's refund credential can move, even after a person says yes.

Written to be read top to bottom and run one file at a time, the way the video does it.

| file | what it is | run it |
|---|---|---|
| `loop.py` | the agent loop with Haiku as the agent, and the guard in the dispatch (`run_tool`); runs a task before and after | `python loop.py C-23 "<request>"` |
| `guard.py` | the guard: rules, then a person for refunds and cancels, or Jev, Sonnet and a person for reversible writes | |
| `rules.py` | layer 1: argument checks, ownership, nothing refunded past what was charged, nothing too late | |
| `jev_guard.py` | layer 2: one Jev `Choice` call, `allow` or `escalate`, two confidence bars, and failing closed | |
| `sonnet_guard.py` | layer 3: Sonnet with a schema-bound reply, `allow`, `deny` or `unsure` | |
| `person.py` | the last layer: a ticket queue in `runs/queue.jsonl` | `python person.py`, `python person.py approve <n>` |
| `calls.py` | a proposed call, a verdict, the one written policy, and the records the guard fetches for itself | |
| `tools.py` | eight read-only lookups, the five writes with their descriptions, and the capped refund credential | |
| `meter.py` | prints each call as it happens and counts model calls, tokens and cost | |
| `funnel.py` | runs labelled calls through the guard and prints what each layer settled, plus the bar sweep | `python funnel.py held_out` |
| `test_guard.py` | offline tests, no model calls | `pytest test_guard.py` |

Every design choice is marked in the code with a `# Decision:` comment.

## About the refund limits

**The $1,000-a-call and $5,000-a-day limits are only for this example.** Follow your own business
use case, your order values and your risk, before you decide a limit. The limits sit on the agent's
refund credential, not in the rules. Every refund that passes the rules already goes to a person,
so a limit doesn't decide who sees a call. It bounds the damage when someone approves one by
mistake, and anything bigger goes through your normal finance process. In this demo the daily total
is a counter in memory; in production it belongs in your payments system.

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

**`calls.json`**, only for `funnel.py`: a list of proposed write calls you've labelled yourself.

```json
[{"id": "t01", "split": "tune", "path": "model", "customer": "C-1", "request": "Hold my order until next week.",
  "name": "hold_shipment", "args": {"order_id": "O-1"}, "label": "run", "why": "the customer asked, the order hasn't shipped"}]
```

`split` is `tune` or `held_out` (pick the bars on `tune`, report on `held_out`), `path` is the layer
you expect the call to reach (`rules`, `person` or `model`), and `label` is `run` or `stop`. The label
is your policy, so write the reason next to it.

Without `data.json` the tests skip and the demo stops with a pointer to this section.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add your TypeSafe and Anthropic keys
pytest test_guard.py      # free, no model calls (needs your data.json)
python loop.py
```

To run on Amazon Bedrock: `pip install "anthropic[bedrock]"`, set up AWS credentials, then use
`anthropic.AnthropicBedrockMantle(aws_region="...")` and the model ids `anthropic.claude-haiku-4-5`
and `anthropic.claude-sonnet-5-5`.

The numbers in the video come from my own runs on 3 Oct 2026 with made-up support data. Your
numbers will look different, so test on your own calls.

MIT licence, see the repository root.
