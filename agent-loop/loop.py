"""The agent loop, written out: call the model, run the tools it asks for, feed the results back."""

import sys
import traceback

import anthropic
from dotenv import load_dotenv

from meter import Meter
from tools import TOOL_SCHEMAS, lookup

load_dotenv()
MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000
# Decision: a hard stop, so a confused model can't go round forever.
MAX_TURNS = 10
SYSTEM = "You are a support agent. Look up what you need with the tools, then answer in three sentences or fewer."

# The same code runs on Amazon Bedrock: swap in anthropic.AnthropicBedrockMantle(aws_region="us-east-1")
# and use the model id "anthropic.claude-sonnet-5".
client = anthropic.Anthropic()


def run_tool(block, meter: Meter) -> dict:
    """Run one tool call and wrap its output as the tool_result Claude reads next turn."""
    meter.lookup(block.name, *block.input.values())
    try:
        output = lookup(block.name, *block.input.values())
    except Exception:
        # Decision: hand the raw traceback back, so the loop keeps going instead of crashing.
        output = traceback.format_exc()
    return {"type": "tool_result", "tool_use_id": block.id, "content": output}


def run_agent(task: str, meter: Meter, run_tool=run_tool) -> str:
    messages = [{"role": "user", "content": task}]
    for _ in range(MAX_TURNS):
        reply = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, tools=TOOL_SCHEMAS, messages=messages
        )
        meter.claude(reply)
        if reply.stop_reason != "tool_use":
            return text_of(reply)
        messages.append({"role": "assistant", "content": reply.content})
        results = [run_tool(block, meter) for block in reply.content if block.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no answer after {MAX_TURNS} turns")


def text_of(reply) -> str:
    return "".join(block.text for block in reply.content if block.type == "text")


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Customer C-17 says their gateway order never arrived. What happened to it?"
    meter = Meter(MODEL)
    print(f"Task: {task}\n")
    print(f"\nAnswer: {run_agent(task, meter)}\n{meter.summary()}")
