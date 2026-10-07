"""The guard: every call that changes state meets the cheapest check that can settle it first.

Rules first, for every write. Then money and one-way doors go to a person. Reversible writes go to
Jev, which lets a call run, sends it to a person when it's very sure it shouldn't run, or else sends it
to Sonnet, which decides or sends it to a person.
"""

import jev_guard
import person
import rules
import sonnet_guard
from calls import ESCALATE, PERSON, RUN, Call, Verdict
from meter import Meter
from tools import ONE_WAY


def guard(call: Call, meter: Meter) -> Verdict:
    stopped = rules.check(call)
    if stopped:
        meter.say(f"rules stopped {call}: {stopped.reason}")
        return stopped
    if call.name in ONE_WAY:
        # Decision: money and one-way doors go to a person at any amount. A limit per call doesn't
        # make small refunds safe: $100 refunds across many accounts are still money moving.
        return person.queue(call, "money or a one-way door, so a person decides", meter)
    verdict = jev_guard.judge(call, meter)
    if verdict.outcome == ESCALATE:
        verdict = sonnet_guard.judge(call, meter)
    if verdict.outcome == PERSON:
        person.queue(call, verdict.reason, meter)
    return verdict


def no_guard(call: Call, meter: Meter) -> Verdict:
    """The loop as it started: every write runs as soon as the model asks for it."""
    return Verdict(RUN, "none", "nothing checks it")
