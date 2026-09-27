"""Change 1, Jev fetches and Claude writes.

Jev picks the lookups and the harness runs them. Claude gets one call with the task and the facts:
no tool schemas, no lookup history, only the writing. If a fact is missing, the plain loop takes over.
"""

import sys

from typesafe_sdk import Noul, TypeSafeClient

from loop import MAX_TOKENS, MODEL, client, run_agent, text_of
from meter import Meter, compare
from tools import TOOLS, candidate_lookups, lookup

# Decision: fetch at 0.7, not higher. A wrong yes costs one wasted read-only lookup;
# a wrong no costs a missing fact and a fall back to the loop.
FETCH_AT = 0.7
MAX_ROUNDS = 4
MISSING = "MISSING:"
WRITER = (
    "You are a support agent. Answer the task from the facts given, in three sentences or fewer. "
    f"If a fact you need is not in the list, reply with only '{MISSING} <what you need>'."
)
jev = TypeSafeClient()


def question(name: str, value: str) -> Noul:
    # Decision: ask literally. "Is this the very next lookup?" splits the probability across
    # lookups that run together; "one of the lookups to run now" does not.
    description, arg, _ = TOOLS[name]
    return Noul(instructions=f"{name}({arg}={value}) is one of the lookups the assistant should run now, "
                             f"possibly alongside others, to complete the task. {name} returns: {description}")


def fetch_facts(task: str, meter: Meter) -> list[str]:
    """Round by round: Jev scores every possible lookup, we run the likely ones, until none are left."""
    facts: list[str] = []
    done: set[tuple[str, str]] = set()
    for _ in range(MAX_ROUNDS):
        candidates = [c for c in candidate_lookups(task + " ".join(facts)) if c not in done]
        if not candidates:
            break
        response = jev.system_one(state={"task": task, "facts": facts},
                                  questions={str(i): question(*c) for i, c in enumerate(candidates)})
        chosen = [c for i, c in enumerate(candidates) if response.nouls[str(i)].noul >= FETCH_AT]
        meter.jev(response, f"{len(chosen)} of {len(candidates)} possible lookups are worth running")
        if not chosen:
            break
        for name, value in chosen:
            meter.lookup(name, value)
            facts.append(f"{name}({value}) -> {lookup(name, value)}")
        done.update(chosen)
    return facts


def jev_fetches(task: str, meter: Meter) -> str:
    facts = fetch_facts(task, meter)
    prompt = f"Task: {task}\n\nFacts:\n" + "\n".join(f"- {fact}" for fact in facts)
    # Decision: no tools and no history on this call. Claude only writes.
    reply = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=WRITER,
                                   messages=[{"role": "user", "content": prompt}])
    meter.claude(reply)
    answer = text_of(reply)
    if answer.startswith(MISSING):
        # Decision: the fallback is the plain loop, so nothing is ever written from missing facts.
        meter.say(f"Claude says {answer!r}, so the plain loop takes over")
        return run_agent(task, meter)
    return answer


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Customer C-17 says their gateway order never arrived. What happened to it?"
    repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    compare(task, MODEL, {"before: the plain loop": run_agent, "after: Jev fetches": jev_fetches}, repeats)
