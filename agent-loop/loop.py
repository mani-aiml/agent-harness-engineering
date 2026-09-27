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

# To run on Amazon Bedrock: pip install "anthropic[bedrock]", set up AWS credentials, then use
# anthropic.AnthropicBedrockMantle(aws_region="us-east-1") and the model id "anthropic.claude-sonnet-5".
client = anthropic.Anthropic()


def raw_traceback(block, error: Exception) -> dict:
    # Decision: hand the raw traceback back, so the loop keeps going instead of crashing.
    return {"type": "tool_result", "tool_use_id": block.id, "content": traceback.format_exc()}


def run_tool(block, meter: Meter, on_error=raw_traceback) -> dict:
    """The dispatch: every tool call Claude makes comes through here before anything runs."""
    name, value = block.name, *block.input.values()
    meter.tool(name, value)
    try:
        return {"type": "tool_result", "tool_use_id": block.id, "content": lookup(name, value)}
    except Exception as error:
        return on_error(block, error)


def run_agent(task: str, meter: Meter, on_error=raw_traceback) -> str:
    messages = [{"role": "user", "content": task}]
    for _ in range(MAX_TURNS):
        reply = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, tools=TOOL_SCHEMAS, messages=messages
        )
        meter.claude(reply)
        if reply.stop_reason != "tool_use":
            return answer_of(reply)
        messages.append({"role": "assistant", "content": reply.content})
        results = [run_tool(block, meter, on_error) for block in reply.content if block.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no answer after {MAX_TURNS} turns")


def answer_of(reply) -> str:
    """The text of a finished reply."""
    if reply.stop_reason != "end_turn":
        # Decision: only end_turn is an answer. max_tokens means the reply was cut off, so say so.
        raise RuntimeError(f"Claude stopped on {reply.stop_reason}, so this is not a finished answer")
    return "".join(block.text for block in reply.content if block.type == "text")


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Customer C-17 says their gateway order never arrived. What happened to it?"
    meter = Meter(MODEL)
    print(f"Task: {task}\n")
    print(f"\nAnswer: {run_agent(task, meter)}\n{meter.summary()}")
