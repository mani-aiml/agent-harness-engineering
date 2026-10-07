"""Offline tests: no model is called. Run with `pytest test_guard.py`."""

from pathlib import Path
from types import SimpleNamespace

import pytest

if not (Path(__file__).parent / "data.json").exists():
    pytest.skip("data.json isn't published: add your own records in the format README.md describes",
                allow_module_level=True)

from typesafe_sdk import TypeSafeAPITimeoutError  # noqa: E402

import guard  # noqa: E402
import jev_guard  # noqa: E402
import loop  # noqa: E402
import person  # noqa: E402
import sonnet_guard  # noqa: E402
import tools  # noqa: E402
from calls import ESCALATE, PERSON, RUN, STOP, Call, Verdict  # noqa: E402
from meter import Meter  # noqa: E402


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(tools, "LOOKUP_SECONDS", 0)
    monkeypatch.setattr(person, "QUEUE", tmp_path / "queue.jsonl")
    tools.reset()


def no_model(*_) -> Verdict:
    raise AssertionError("this call should never reach a model")


def judged(outcome: str):
    return lambda call, meter: Verdict(outcome, "test", "stub")


def decide(name: str, customer: str = "C-23", **args) -> Verdict:
    return guard.guard(Call(name, args, customer, "test request"), Meter(quiet=True))


@pytest.mark.parametrize("name, customer, args, why", [
    ("issue_refund", "C-17", {"order_id": "O-1051", "amount": 249.0}, "C-23's account"),
    ("issue_refund", "C-23", {"order_id": "O-1051", "amount": 600.0}, "charged and not yet refunded"),
    ("issue_refund", "C-17", {"order_id": "O-1077", "amount": 10.0}, "charged and not yet refunded"),
    ("cancel_order", "C-17", {"order_id": "O-1042"}, "already shipped"),
    ("update_email", "C-23", {"customer_id": "C-23", "email": "not-an-email"}, "valid email"),
    ("update_address", "C-23", {"order_id": "O-1051", "address": "1 New Street, Austin"}, "already delivered"),
    ("hold_shipment", "C-23", {"order_id": "1051"}, "valid order id"),
])
def test_rules_stop_the_obvious_calls(monkeypatch, name, customer, args, why) -> None:
    monkeypatch.setattr(jev_guard, "judge", no_model)
    verdict = decide(name, customer, **args)
    assert (verdict.outcome, verdict.layer) == (STOP, "rules")
    assert why in verdict.reason


@pytest.mark.parametrize("name, customer, args", [
    ("issue_refund", "C-23", {"order_id": "O-1051", "amount": 1.0}),
    ("issue_refund", "C-23", {"order_id": "O-1051", "amount": 498.0}),
    ("cancel_order", "C-31", {"order_id": "O-1090"}),
])
def test_money_and_one_way_doors_go_to_a_person_at_any_amount(monkeypatch, name, customer, args) -> None:
    monkeypatch.setattr(jev_guard, "judge", no_model)
    monkeypatch.setattr(sonnet_guard, "judge", no_model)
    assert decide(name, customer, **args).outcome == PERSON
    assert len(person.tickets()) == 1


def test_jev_above_the_bar_runs_a_reversible_write(monkeypatch) -> None:
    monkeypatch.setattr(jev_guard, "judge", judged(RUN))
    monkeypatch.setattr(sonnet_guard, "judge", no_model)
    assert decide("hold_shipment", "C-31", order_id="O-1090").outcome == RUN


@pytest.mark.parametrize("sonnet, expected, tickets", [(RUN, RUN, 0), (STOP, STOP, 0), (PERSON, PERSON, 1)])
def test_what_jev_sends_up_goes_to_sonnet_then_a_person(monkeypatch, sonnet, expected, tickets) -> None:
    monkeypatch.setattr(jev_guard, "judge", judged(ESCALATE))
    monkeypatch.setattr(sonnet_guard, "judge", judged(sonnet))
    assert decide("update_email", "C-23", customer_id="C-23", email="m.hill@example.org").outcome == expected
    assert len(person.tickets()) == tickets


def test_jev_very_sure_it_should_not_run_goes_straight_to_a_person(monkeypatch) -> None:
    monkeypatch.setattr(jev_guard, "judge", judged(PERSON))
    monkeypatch.setattr(sonnet_guard, "judge", no_model)
    assert decide("update_email", "C-23", customer_id="C-23", email="m.hill@example.org").outcome == PERSON
    assert len(person.tickets()) == 1


@pytest.mark.parametrize("confidence, expected", [(0.9, PERSON), (jev_guard.PERSON_AT, PERSON), (0.5, ESCALATE)])
def test_how_sure_jev_is_picks_a_person_or_sonnet(monkeypatch, confidence, expected) -> None:
    monkeypatch.setattr(jev_guard, "ask", lambda call, meter: SimpleNamespace(choice="escalate", confidence=confidence))
    verdict = jev_guard.judge(Call("hold_shipment", {"order_id": "O-1090"}, "C-31", "hold it"), Meter(quiet=True))
    assert verdict.outcome == expected


def test_jev_fails_closed(monkeypatch) -> None:
    def times_out(**_):
        raise TypeSafeAPITimeoutError("timed out")
    monkeypatch.setattr(jev_guard.jev, "system_one", times_out)
    verdict = jev_guard.judge(Call("hold_shipment", {"order_id": "O-1090"}, "C-31", "hold it"), Meter(quiet=True))
    assert verdict.outcome == ESCALATE


def test_the_credential_caps_a_refund_a_person_approved() -> None:
    with pytest.raises(tools.OverLimit, match="finance"):
        tools.call_tool("issue_refund", {"order_id": "O-1063", "amount": 5200.0}, "C-31")
    with pytest.raises(tools.OverLimit, match="scoped to C-17"):
        tools.call_tool("issue_refund", {"order_id": "O-1051", "amount": 10.0}, "C-17")
    assert tools.CHANGES == []


def test_the_credential_caps_the_day_across_accounts(monkeypatch) -> None:
    monkeypatch.setattr(tools, "refunded_today", 4_900.0)
    with pytest.raises(tools.OverLimit):
        tools.call_tool("issue_refund", {"order_id": "O-1051", "amount": 249.0}, "C-23")


def test_a_write_that_is_not_run_comes_back_as_one_clear_error() -> None:
    block = SimpleNamespace(id="toolu_1", name="issue_refund", input={"order_id": "O-1051", "amount": 249.0})
    result = loop.run_tool(block, "C-17", "refund me", Meter(quiet=True))
    assert result["is_error"] and "did not run" in result["content"]
    assert tools.CHANGES == []
