"""Offline tests: no model is called. Run with `pytest test_changes.py`."""

from types import SimpleNamespace

import pytest

import loop
import router
import tool_returns
import tools
from jev_fetches import question
from meter import Meter


@pytest.fixture(autouse=True)
def fast_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "LOOKUP_SECONDS", 0)


def shipment_call() -> SimpleNamespace:
    return SimpleNamespace(id="toolu_1", name="get_shipment", input={"order_id": "O-1042"})


def test_candidates_come_from_the_ids_in_the_text() -> None:
    candidates = tools.candidate_lookups("Customer C-17, order O-1042")
    assert ("get_customer", "C-17") in candidates
    assert ("get_shipment", "O-1042") in candidates
    assert not any(value == "SKU-301" for _, value in candidates)


def test_the_jev_question_is_asked_literally() -> None:
    assert "possibly alongside others" in question("get_order", "O-1042").instructions


def test_the_plain_loop_hands_back_the_raw_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "carrier_down", True)
    result = loop.run_tool(shipment_call(), Meter(loop.MODEL, quiet=True))
    assert "Traceback" in result["content"] and "is_error" not in result


def test_the_clear_return_is_one_sentence_flagged_as_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "carrier_down", True)
    result = loop.run_tool(shipment_call(), Meter(loop.MODEL, quiet=True), on_error=tool_returns.clear_error)
    assert result["is_error"] is True and "Traceback" not in result["content"]


def test_an_unsure_router_falls_back_to_the_plain_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "run_agent", lambda task, meter: "plain loop")
    unsure = lambda task, meter: ("policy", 0.5)  # noqa: E731
    assert router.routed("anything", Meter(loop.MODEL, quiet=True), router=unsure) == "plain loop"


def test_actions_go_to_a_person_without_any_model_call() -> None:
    meter = Meter(loop.MODEL, quiet=True)
    sure_human = lambda task, m: ("human", 0.99)  # noqa: E731
    assert router.routed("Refund O-1051", meter, router=sure_human).startswith("Handed to a person")
    assert meter.claude_calls == 0


def test_only_end_turn_counts_as_an_answer() -> None:
    text = [SimpleNamespace(type="text", text="cut off mid")]
    assert loop.answer_of(SimpleNamespace(stop_reason="end_turn", content=text)) == "cut off mid"
    with pytest.raises(RuntimeError, match="max_tokens"):
        loop.answer_of(SimpleNamespace(stop_reason="max_tokens", content=text))
