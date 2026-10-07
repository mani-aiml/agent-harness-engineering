"""Counts what a run costs and prints it as it happens: model calls, tokens, tool calls, seconds."""

import time

# USD per million tokens, input and output. Anthropic's price list, and TypeSafe's for Jev
# (input only; Jev's output tokens are free), both as of 3 Oct 2026.
CLAUDE_USD = {"claude-haiku-4-5": (1.00, 5.00), "claude-sonnet-5-5": (2.00, 10.00)}
JEV_USD_IN = 0.042


def price(model: str) -> tuple[float, float]:
    """The price row for a reply's model id, which may carry a date suffix."""
    return next(usd for name, usd in CLAUDE_USD.items() if model.startswith(name))


class Meter:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self.claude_calls = self.input_tokens = self.jev_calls = self.jev_tokens = self.tool_calls = 0
        self.claude_usd = 0.0
        self.started = time.perf_counter()
        self.lines: list[str] = []

    def say(self, line: str) -> None:
        self.lines.append(line)
        if not self.quiet:
            print(f"  {time.perf_counter() - self.started:5.1f}s  {line}")

    def claude(self, reply, note: str = "") -> None:
        usd_in, usd_out = price(reply.model)
        self.claude_calls += 1
        self.input_tokens += reply.usage.input_tokens
        self.claude_usd += (reply.usage.input_tokens * usd_in + reply.usage.output_tokens * usd_out) / 1e6
        asks = [f"{b.name}({', '.join(map(str, b.input.values()))})" for b in reply.content if b.type == "tool_use"]
        did = note or ("asks for " + ", ".join(asks) if asks else "answers")
        self.say(f"Claude call {self.claude_calls}: {did}")

    def jev(self, response, note: str) -> None:
        self.jev_calls += 1
        self.jev_tokens += response.usage.input_tokens
        self.say(f"Jev call {self.jev_calls}: {note}")

    def tool(self, name: str, args: dict) -> None:
        self.tool_calls += 1
        self.say(f"tool {name}({', '.join(map(str, args.values()))})")

    @property
    def usd(self) -> float:
        return self.claude_usd + self.jev_tokens * JEV_USD_IN / 1e6

    def summary(self) -> str:
        return (f"{self.claude_calls} Claude calls · {self.jev_calls} Jev calls · "
                f"{self.tool_calls} tool calls · ${self.usd:.4f}")
