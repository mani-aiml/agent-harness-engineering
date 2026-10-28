"""Layer 2, Jev: one fast call that lets a reversible write run, or sends it up.

Jev is a decision model from TypeSafe AI: it returns a typed choice and a confidence, and writes
nothing. It only ever sees reversible writes, because money and one-way doors go to a person.
"""

from dotenv import load_dotenv
from langfuse import observe
from typesafe_sdk import Choice, TypeSafeClient, TypeSafeError

from calls import ESCALATE, POLICY, RUN, Call, Verdict, state

# Decision: Jev never says no. A wrong yes is the expensive mistake, so its only options are to
# let the call run or to send it to a person.
CRITERIA = {"allow": POLICY["allowed"], "escalate": POLICY["not allowed"]}
# Decision: the bar comes from the labelled tuning calls, not from feel. It's the lowest bar at which Jev
# let no unsafe call run (runs/sweep_2026-10-03.txt). There it trades only how many safe calls get
# automated: 9 of 14 at 0.5, 4 of 14 at 0.9.
GUARD_AT = 0.5
# Decision: Jev answers in a fraction of a second, so a call that takes longer than this has gone wrong.
JEV_TIMEOUT = 3.0
load_dotenv()
jev = TypeSafeClient()


# Jev's choice and its confidence, next to the bar it was held to.
@observe(as_type="guardrail", name="jev")
def ask(call: Call):
    """One Jev call: its choice for this call, with a confidence and both probabilities."""
    response = jev.system_one(state=state(call), timeout=JEV_TIMEOUT, questions={"guard": Choice(
        instructions="Should this support agent's proposed tool call run now?", criteria=CRITERIA)})
    return response.choices["guard"]


def lets_run(answer, bar: float = GUARD_AT) -> bool:
    """The one rule for letting a call run: Jev chose allow, with a confidence at or above the bar."""
    return answer.choice == "allow" and answer.confidence >= bar


def judge(call: Call) -> Verdict:
    try:
        answer = ask(call)
    except TypeSafeError as error:
        # Decision: the guard fails closed. If Jev errors or times out, the call goes up, never through.
        return Verdict(ESCALATE, "jev", f"Jev failed: {type(error).__name__}")
    if lets_run(answer):
        return Verdict(RUN, "jev", f"allow at {answer.confidence:.2f}")
    if answer.choice == "allow":
        return Verdict(ESCALATE, "jev", f"allow at {answer.confidence:.2f}, under the bar of {GUARD_AT}")
    return Verdict(ESCALATE, "jev", f"escalate at {answer.confidence:.2f}")
