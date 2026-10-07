"""Layer 3, Sonnet: the bigger model, only for the reversible writes Jev sent up.

To run on Amazon Bedrock: pip install "anthropic[bedrock]", set up AWS credentials, then use
anthropic.AnthropicBedrockMantle(aws_region="us-east-1") and the model id "anthropic.claude-sonnet-5-5".
"""

import json

import anthropic
from dotenv import load_dotenv

from calls import PERSON, POLICY, RUN, STOP, Call, Verdict, state
from meter import Meter

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000
# Decision: low effort. Sonnet makes one short decision on a call Jev sent up, so deep thinking only adds
# cost and seconds.
EFFORT = "low"
SYSTEM = (
    "You review one tool call a customer support agent wants to make, using only the customer's request, "
    f"the records and this policy.\nAllowed: {POLICY['allowed']}\nNot allowed: {POLICY['not allowed']}\n"
    "Answer allow when the policy allows it, deny when the policy doesn't, and unsure when a person should "
    "look at it. Give one short reason."
)
# Decision: the reply is held to this schema, so the harness reads a decision, not free text.
DECISION = {"type": "json_schema", "schema": {
    "type": "object", "additionalProperties": False, "required": ["decision", "reason"],
    "properties": {"decision": {"type": "string", "enum": ["allow", "deny", "unsure"]},
                   "reason": {"type": "string"}}}}
OUTCOMES = {"allow": RUN, "deny": STOP, "unsure": PERSON}
load_dotenv()
client = anthropic.Anthropic()


def judge(call: Call, meter: Meter) -> Verdict:
    reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM,
                                   output_config={"format": DECISION, "effort": EFFORT},
                                   messages=[{"role": "user", "content": json.dumps(state(call))}])
    if reply.stop_reason != "end_turn":
        # Decision: fail closed here too. A refusal or a cut-off reply goes to a person.
        meter.claude(reply, f"{call}: stopped on {reply.stop_reason}, so a person decides")
        return Verdict(PERSON, "sonnet", f"Sonnet stopped on {reply.stop_reason}")
    decision = json.loads(next(block.text for block in reply.content if block.type == "text"))
    meter.claude(reply, f"{call}: {decision['decision']} ({decision['reason']})")
    return Verdict(OUTCOMES[decision["decision"]], "sonnet", decision["reason"])
