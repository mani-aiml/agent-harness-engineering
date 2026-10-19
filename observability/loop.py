"""A support agent with a guard on its writes, traced: every step it takes shows up in Langfuse.

Run it: python loop.py C-23 "I was charged twice for order O-1051, please refund me."
Then open http://localhost:3000 and read the trace.
"""

import sys

import anthropic
from langfuse import get_client, observe, propagate_attributes

import tools
from calls import PERSON, RUN, Call, Verdict
from guard import guard
from tools import TODAY, TOOL_SCHEMAS, WRITES, OverLimit, call_tool

# Decision: a small open model, running on this laptop through Ollama, which speaks the same API as Claude.
# ANTHROPIC_BASE_URL in .env points the client at it; for Claude, drop that line and use "claude-haiku-4-5".
MODEL = "qwen3:4b"
MAX_TOKENS = 16000
# Decision: a hard stop, so a confused model can't go round forever.
MAX_TURNS = 10
# Decision: the system prompt only points at the tools. Each tool's own description says what to look
# up first and when it may be used, so the rules travel with the tool, not with this prompt.
SYSTEM = (f"You are a support agent. Today is {TODAY}. Before you call any tool that changes something, "
          "follow that tool's description: run the lookups it lists first, in the order it lists them, and "
          "only make the change when the description allows it. Then answer in three sentences or fewer.")

# To run on Amazon Bedrock: pip install "anthropic[bedrock]", set up AWS credentials, then use
# anthropic.AnthropicBedrockMantle(aws_region="us-east-1") and the model id "anthropic.claude-haiku-4-5".
# Every Claude call becomes a span with its tokens and time. "content" adds what the model saw and said.
client = anthropic.Anthropic(open_telemetry={"traces": {"content_mode": "content"}})


def not_run(block, call: Call, verdict: Verdict) -> dict:
    # Decision: one clear sentence, flagged as an error, so the model tells the customer the truth.
    if verdict.outcome == PERSON:
        text = f"{call} is waiting for a person on the team. Don't try again. Tell the customer someone will follow up."
    else:
        text = f"{call} did not run: {verdict.reason}. Don't try again. Tell the customer what you can do instead."
    return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": text}


# Decision: the SDK only traces the model calls. Your tools and your guard are your code, so you name them.
@observe(as_type="tool")
def run_tool(block, customer: str, request: str) -> dict:
    """The dispatch: every tool call the model makes comes through here before anything runs."""
    get_client().update_current_span(name=block.name)  # the trace shows get_order, issue_refund, not run_tool
    if block.name in WRITES:
        # Decision: the gate lives here, not in a router. A refund often shows up only after the lookups.
        call = Call(block.name, block.input, customer, request)
        verdict = guard(call)
        if verdict.outcome != RUN:
            return not_run(block, call, verdict)
    try:
        return {"type": "tool_result", "tool_use_id": block.id, "content": call_tool(block.name, block.input, customer)}
    except OverLimit as refused:
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"Refused: {refused}."}


# One trace per customer request, with every step nested under it.
@observe(as_type="agent")
def run_agent(request: str, customer: str) -> str:
    # Decision: the customer comes from the signed-in session, never from the model.
    messages = [{"role": "user", "content": f"Customer {customer} writes: {request}"}]
    for _ in range(MAX_TURNS):
        reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
                                       tools=TOOL_SCHEMAS, messages=messages)
        if reply.stop_reason != "tool_use":
            return answer_of(reply)
        messages.append({"role": "assistant", "content": reply.content})
        results = [run_tool(b, customer, request) for b in reply.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no answer after {MAX_TURNS} turns")


def answer_of(reply) -> str:
    """The text of a finished reply."""
    if reply.stop_reason != "end_turn":
        # Decision: only end_turn is an answer. max_tokens means the reply was cut off, so say so.
        raise RuntimeError(f"the model stopped on {reply.stop_reason}, so this is not a finished answer")
    return "".join(block.text for block in reply.content if block.type == "text")


if __name__ == "__main__":
    customer = sys.argv[1] if len(sys.argv) > 1 else "C-23"
    request = sys.argv[2] if len(sys.argv) > 2 else "I was charged twice for order O-1051, please refund me."
    # Decision: tag the trace with the customer, so "what happened to C-23 yesterday" is a filter.
    with propagate_attributes(user_id=customer):
        print(f"answer: {run_agent(request, customer)}")
    print(f"writes that actually ran: {tools.CHANGES or 'none'}. Every step is in Langfuse.")
