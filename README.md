# agent-harness-engineering

Design patterns for the code around an agent's loop: what you add, move or change once the
framework's default loop is running. One folder per pattern, each with runnable code, its own
README, and the numbers from my runs. The videos are in the Agent Harness Engineering playlist
on The Agentic Enterprise on YouTube.

| folder | pattern |
|---|---|
| [`agent-loop/`](agent-loop/) | the agent loop written out in about twelve lines, then three changes to it: Jev fetches and Claude writes, a router in front of the loop, and one clear sentence instead of a raw traceback when a tool fails |

```bash
cd <folder>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add the keys that folder's README names
```

All data in these demos is synthetic, made up for the demo it sits in and for nothing else. Any
resemblance to real people, companies or records is purely coincidental.

MIT licence for everything here.
