"""The guard: every call that changes state meets the cheapest check that can settle it first.

Rules first, for every write. Then money and one-way doors go to a person. Reversible writes go to
Jev, which lets a call run or sends it to a person.
"""

from langfuse import observe

import jev_guard
import person
import rules
from calls import ESCALATE, Call, Verdict
from tools import ONE_WAY


# Which layer settled the call, and why.
@observe(as_type="guardrail")
def guard(call: Call) -> Verdict:
    stopped = rules.check(call)
    if stopped:
        return stopped
    if call.name in ONE_WAY:
        # Decision: money and one-way doors go to a person at any amount. A limit per call doesn't
        # make small refunds safe: $100 refunds across many accounts are still money moving.
        return person.queue(call, "money or a one-way door, so a person decides")
    verdict = jev_guard.judge(call)
    if verdict.outcome == ESCALATE:
        return person.queue(call, verdict.reason)
    return verdict

