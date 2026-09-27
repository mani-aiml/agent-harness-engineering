"""Counts what a run costs and prints it as it happens: model calls, tokens, lookups, seconds."""

import statistics
import time
from typing import Callable

# USD per million tokens, input and output. Anthropic's price list, and TypeSafe's for Jev
# (input only; Jev's output tokens are free), both as of Sep 2026.
CLAUDE_USD = {"claude-sonnet-5": (2.00, 10.00)}
JEV_USD_IN = 0.042
FORMATS = {"seconds": ".1f", "Claude calls": ".0f", "input tokens": ",.0f", "tool calls": ".0f", "USD": ".5f"}


class Meter:
    def __init__(self, model: str, quiet: bool = False) -> None:
        self.model, self.quiet = model, quiet
        self.claude_calls = self.input_tokens = self.output_tokens = 0
        self.jev_calls = self.jev_tokens = self.tool_calls = 0
        self.started = time.perf_counter()

    def say(self, line: str) -> None:
        if not self.quiet:
            print(f"  {time.perf_counter() - self.started:5.1f}s  {line}")

    def claude(self, reply) -> None:
        self.claude_calls += 1
        self.input_tokens += reply.usage.input_tokens
        self.output_tokens += reply.usage.output_tokens
        asks = [f"{b.name}({next(iter(b.input.values()), '')})" for b in reply.content if b.type == "tool_use"]
        did = "asks for " + ", ".join(asks) if asks else "answers"
        self.say(f"Claude call {self.claude_calls}: {did}   ({self.input_tokens:,} input tokens so far)")

    def jev(self, response, note: str) -> None:
        self.jev_calls += 1
        self.jev_tokens += response.usage.input_tokens
        self.say(f"Jev call {self.jev_calls}: {note}")

    def tool(self, name: str, value: str) -> None:
        self.tool_calls += 1
        self.say(f"tool {name}({value})")

    @property
    def usd(self) -> float:
        usd_in, usd_out = CLAUDE_USD[self.model]
        claude = (self.input_tokens * usd_in + self.output_tokens * usd_out) / 1e6
        return claude + self.jev_tokens * JEV_USD_IN / 1e6

    def summary(self) -> str:
        return (f"{self.claude_calls} Claude calls · {self.input_tokens:,} input tokens · "
                f"{self.tool_calls} tool calls · ${self.usd:.4f}")

    def row(self) -> dict[str, float]:
        return {"seconds": time.perf_counter() - self.started, "Claude calls": self.claude_calls,
                "input tokens": self.input_tokens, "tool calls": self.tool_calls, "USD": self.usd}


def compare(task: str, model: str, arms: dict[str, Callable[[str, Meter], str]], repeats: int = 1) -> None:
    """Run each arm on the same task. One run prints live; more runs print medians only."""
    print(f"\nTask: {task}")
    rows: dict[str, list[dict[str, float]]] = {name: [] for name in arms}
    for _ in range(repeats):
        for name, arm in arms.items():
            meter = Meter(model, quiet=repeats > 1)
            if repeats == 1:
                print(f"\n{name}")
            answer = arm(task, meter)
            meter.say(f"answer: {answer}")
            rows[name].append(meter.row())
    label = f"median of {repeats} runs" if repeats > 1 else "this run"
    print(f"\n{label:<28}" + "".join(f"{key:>14}" for key in FORMATS))
    for name, runs in rows.items():
        medians = {key: statistics.median(run[key] for run in runs) for key in FORMATS}
        print(f"{name:<28}" + "".join(f"{format(medians[key], fmt):>14}" for key, fmt in FORMATS.items()))
