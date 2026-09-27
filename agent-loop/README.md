# The agent loop, and three changes to it

The code behind the video "Every framework gives you the loop. Production is changing it."
Written to be read top to bottom and run one file at a time, the way the video does it.

| file | what it is | run it |
|---|---|---|
| `loop.py` | the agent loop in about twelve lines: call Claude, run the tools it asks for, send the results back, repeat | `python loop.py` |
| `jev_fetches.py` | change 1: Jev picks the lookups, Claude writes once with no tools and no history, the plain loop is the fallback | `python jev_fetches.py` |
| `router.py` | change 2: Jev picks the path first (look up records, answer from policy, or hand to a person, which in this demo is a printed line); also Jev and Claude making the same routing decision | `python router.py`, or `python router.py "<task>"` |
| `tool_returns.py` | change 3: when a tool fails, send back one clear sentence flagged as an error instead of the raw traceback | `python tool_returns.py` |
| `tools.py` | eight read-only lookups over `data.json`, with a switch for a carrier outage. Nothing here changes state, so no path can move money | |
| `meter.py` | prints each call as it happens and counts Claude calls, tokens, lookups and cost | |
| `test_changes.py` | offline tests, no model calls | `pytest test_changes.py` |

Every design choice is marked in the code with a `# Decision:` comment.

## What I measured

27 Sep 2026, `claude-sonnet-5`, anthropic 1.7.0, typesafe-sdk 0.7.1, lookups simulated at 0.5 s,
medians of three runs. Full output in `runs/medians_2026-09-27.txt`.

| change | before | after |
|---|---|---|
| 1, Jev fetches (gateway order task) | 4 Claude calls, 5,392 input tokens | 1 Claude call, 437 input tokens |
| 2, router (UK refund policy question) | 2 Claude calls, 2,221 input tokens | 1 Claude call, 192 input tokens |
| 2, router (refund request) | 4 Claude calls, 5,603 input tokens | 0 Claude calls, handed to a person |
| 3, clear tool returns (carrier timeout, 10 runs each) | 1 or 2 additional calls in 4 of 10 runs (2 to 4 calls) | 2 calls in all 10 |

Routing the same seven requests: Jev and Claude picked the same path on all seven. Jev took
0.17 s and $0.000016 per decision, Claude 1.23 s and $0.00035, and Jev also returns a confidence.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add your TypeSafe and Anthropic keys
pytest test_changes.py    # free, no model calls
python loop.py
```

A full pass through the four files costs a few cents on Claude and a fraction of a cent on Jev.

To run on Amazon Bedrock: `pip install "anthropic[bedrock]"`, set up AWS credentials, then use
`anthropic.AnthropicBedrockMantle(aws_region="...")` and the model id `anthropic.claude-sonnet-5`.

## Read this before trusting the numbers

- Three runs each (ten for change 3, `runs/retry_rate_2026-09-27.txt`), on made-up support data. Claude takes
  different paths from run to run: with the raw traceback it took extra calls in 4 of 10 runs,
  so a single run may not show it. The token figures in that file are upper-middle values, not
  medians; the probe now saves every run's tokens.
- The loop returns only on `end_turn`; any other stop reason, like `max_tokens`, raises.
- The missing-fact fallback in `jev_fetches.py` fires only when Claude starts its reply with
  `MISSING:`. It is an instruction, so test that Claude follows it on your tasks.
- Not every clear error message helps. In a side test, a "helpful" message for an order id in the
  wrong format made Claude take one more turn, not one fewer. Test each message on your own runs.
- The records are synthetic, made up for this demo and for nothing else. Any resemblance to real
  people, companies, orders or records is purely coincidental.

MIT licence, see the repository root.
