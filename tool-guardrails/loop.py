"""The agent loop, with a guard in the dispatch: every call that changes state is checked first.

Run it: python loop.py C-23 "I was charged twice for order O-1051, please refund me."
It runs the task twice, with nothing checking the writes and then with the guard, and prints
which writes actually ran each time.
"""

import sys

import anthropic

import tools
from calls import PERSON, RUN, Call, Verdict
from guard import guard, no_guard
from meter import Meter
from tools import TODAY, TOOL_SCHEMAS, WRITES, OverLimit, call_tool

MODEL = "claude-haiku-4-5"
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
client = anthropic.Anthropic()


def not_run(block, call: Call, verdict: Verdict) -> dict:
    # Decision: one clear sentence, flagged as an error, so the model tells the customer the truth.
    if verdict.outcome == PERSON:
        text = f"{call} is waiting for a person on the team. Don't try again. Tell the customer someone will follow up."
    else:
        text = f"{call} did not run: {verdict.reason}. Don't try again. Tell the customer what you can do instead."
    return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": text}


def run_tool(block, customer: str, request: str, meter: Meter, gate=guard) -> dict:
    """The dispatch: every tool call the model makes comes through here before anything runs."""
    meter.tool(block.name, block.input)
    if block.name in WRITES:
        # Decision: the gate lives here, not in a router. A refund often shows up only after the lookups.
        call = Call(block.name, block.input, customer, request)
        verdict = gate(call, meter)
        if verdict.outcome != RUN:
            return not_run(block, call, verdict)
    try:
        return {"type": "tool_result", "tool_use_id": block.id, "content": call_tool(block.name, block.input, customer)}
    except OverLimit as refused:
        meter.say(f"the credential refused {block.name}: {refused}")
        return {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"Refused: {refused}."}


def run_agent(request: str, customer: str, meter: Meter, gate=guard) -> str:
    # Decision: the customer comes from the signed-in session, never from the model.
    messages = [{"role": "user", "content": f"Customer {customer} writes: {request}"}]
    for _ in range(MAX_TURNS):
        reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
                                       tools=TOOL_SCHEMAS, messages=messages)
        meter.claude(reply)
        if reply.stop_reason != "tool_use":
            return answer_of(reply)
        messages.append({"role": "assistant", "content": reply.content})
        results = [run_tool(b, customer, request, meter, gate) for b in reply.content if b.type == "tool_use"]
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
    for label, gate in {"before: nothing checks the writes": no_guard, "after: the guard": guard}.items():
        tools.reset()
        meter = Meter()
        print(f"\n{label}")
        meter.say(f"answer: {run_agent(request, customer, meter, gate)}")
        print(f"  writes that actually ran: {tools.CHANGES or 'none'}\n  {meter.summary()}")
