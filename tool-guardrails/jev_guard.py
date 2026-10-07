"""Layer 2, Jev: one fast call that lets a reversible write run, or sends it up.

Jev is a decision model from TypeSafe AI: it returns a typed choice and a confidence, and writes
nothing. It only ever sees reversible writes, because money and one-way doors go to a person.
"""

from dotenv import load_dotenv
from typesafe_sdk import Choice, TypeSafeClient, TypeSafeError

from calls import ESCALATE, PERSON, POLICY, RUN, Call, Verdict, state
from meter import Meter

# Decision: Jev never says no. A wrong yes is the expensive mistake, so its only options are to
# let the call run or to send it to a bigger model.
CRITERIA = {"allow": POLICY["allowed"], "escalate": POLICY["not allowed"]}
# Decision: the bar comes from the labelled tuning calls, not from feel. It's the lowest bar at which Jev
# let no unsafe call run (runs/sweep_2026-10-03.txt). There it trades only how many safe calls get
# automated: 9 of 14 at 0.5, 4 of 14 at 0.9.
GUARD_AT = 0.5
# Decision: when Jev escalates and is very sure, a person decides, not a bigger model. This bar also comes
# from the tuning calls: the lowest bar at which no safe call went straight to a person
# (runs/replay_person_at_2026-10-04.txt). Below it, the call goes to Sonnet.
PERSON_AT = 0.7
# Decision: Jev answers in a fraction of a second, so a call that takes longer than this has gone wrong.
JEV_TIMEOUT = 3.0
load_dotenv()
jev = TypeSafeClient()


def ask(call: Call, meter: Meter):
    """One Jev call: its choice for this call, with a confidence and both probabilities."""
    response = jev.system_one(state=state(call), timeout=JEV_TIMEOUT, questions={"guard": Choice(
        instructions="Should this support agent's proposed tool call run now?", criteria=CRITERIA)})
    answer = response.choices["guard"]
    meter.jev(response, f"{call}: {answer.choice} (confidence {answer.confidence:.2f})")
    return answer


def lets_run(answer, bar: float = GUARD_AT) -> bool:
    """The one rule for letting a call run: Jev chose allow, with a confidence at or above the bar."""
    return answer.choice == "allow" and answer.confidence >= bar


def judge(call: Call, meter: Meter) -> Verdict:
    try:
        answer = ask(call, meter)
    except TypeSafeError as error:
        # Decision: the guard fails closed. If Jev errors or times out, the call goes up, never through.
        meter.say(f"Jev failed ({type(error).__name__}), so {call} goes up")
        return Verdict(ESCALATE, "jev", f"Jev failed: {type(error).__name__}")
    if lets_run(answer):
        return Verdict(RUN, "jev", f"allow at {answer.confidence:.2f}")
    if answer.choice == "allow":
        return Verdict(ESCALATE, "jev", f"allow at {answer.confidence:.2f}, under the bar of {GUARD_AT}")
    if answer.confidence >= PERSON_AT:
        return Verdict(PERSON, "jev", f"escalate at {answer.confidence:.2f}, so a person decides")
    return Verdict(ESCALATE, "jev", f"escalate at {answer.confidence:.2f}")
