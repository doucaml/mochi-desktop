"""The agent activity tracker turns hook lifecycle words into presentation edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from mochi.agent_activity import (
    AGENT_EVENTS,
    AGENT_TOKEN_PATTERN,
    AgentActivityTracker,
    AgentEdge,
)

A = "0123456789abcdef"
GRACE = AgentActivityTracker.NEEDS_INPUT_GRACE_SECONDS
B = "fedcba9876543210"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def tracker(clock: FakeClock) -> AgentActivityTracker:
    return AgentActivityTracker(clock=clock)


def test_allow_list_and_token_shape_are_the_shared_contract() -> None:
    assert AGENT_EVENTS == {
        "working",
        "activity",
        "needs_input",
        "prompt_waiting",
        "finished",
        "ended",
    }
    assert AGENT_TOKEN_PATTERN.fullmatch(A)
    assert not AGENT_TOKEN_PATTERN.fullmatch(A.upper())
    assert not AGENT_TOKEN_PATTERN.fullmatch(A + "0")


def test_first_working_session_starts_work_and_second_adds_no_edge(tracker) -> None:
    assert tracker.record("working", A) == [AgentEdge.WORK_STARTED]
    assert tracker.record("working", B) == []
    assert tracker.record("working", A) == []
    assert tracker.working
    assert tracker.has_sessions


def test_long_run_finish_stops_then_celebrates(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 61.0

    assert tracker.record("finished", A) == [
        AgentEdge.WORK_STOPPED,
        AgentEdge.FINISHED_LONG,
    ]
    assert not tracker.working
    assert not tracker.has_sessions


def test_short_run_finish_only_stops(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 59.0

    assert tracker.record("finished", A) == [AgentEdge.WORK_STOPPED]


def test_quick_approval_inside_grace_produces_no_edges(tracker, clock) -> None:
    tracker.record("working", A)

    assert tracker.record("needs_input", A) == []
    clock.now = 5.0
    assert tracker.poll() == []
    assert tracker.record("activity", A) == []
    clock.now = GRACE + 20.0
    assert tracker.poll() == []
    assert tracker.working


def test_unanswered_prompt_nudges_once_after_grace(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 1.0
    tracker.record("needs_input", A)
    clock.now = 1.0 + GRACE - 0.1
    assert tracker.poll() == []
    assert tracker.working

    clock.now = 1.0 + GRACE
    assert tracker.poll() == [AgentEdge.WORK_STOPPED, AgentEdge.NEEDS_INPUT]
    assert not tracker.working
    clock.now = 2 * GRACE
    assert tracker.poll() == []
    assert tracker.record("needs_input", A) == []
    assert tracker.poll() == []


def test_late_approval_restarts_work_and_allows_a_second_nudge(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("needs_input", A)
    clock.now = GRACE
    tracker.poll()

    clock.now = GRACE + 30.0
    assert tracker.record("activity", A) == [AgentEdge.WORK_STARTED]
    tracker.record("needs_input", A)
    clock.now = 2 * GRACE + 30.0
    assert tracker.poll() == [AgentEdge.WORK_STOPPED, AgentEdge.NEEDS_INPUT]


def test_working_event_also_ends_a_wait(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("needs_input", A)
    clock.now = 3.0

    assert tracker.record("working", A) == []
    clock.now = 3.0 + 2 * GRACE
    assert tracker.poll() == []


def test_finish_while_waiting_never_celebrates(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 100.0
    tracker.record("needs_input", A)
    clock.now = 105.0

    assert tracker.record("finished", A) == [AgentEdge.WORK_STOPPED]


def test_ended_never_celebrates(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 600.0

    assert tracker.record("ended", A) == [AgentEdge.WORK_STOPPED]
    assert not tracker.has_sessions


def test_unknown_session_activity_finished_ended_are_ignored(tracker) -> None:
    assert tracker.record("activity", A) == []
    assert tracker.record("finished", A) == []
    assert tracker.record("ended", A) == []
    assert not tracker.has_sessions
    assert not tracker.working


def test_needs_input_from_unknown_session_still_nudges(tracker, clock) -> None:
    # Mochi restarted mid-run: the next permission prompt still reaches the user.
    assert tracker.record("needs_input", A) == [AgentEdge.WORK_STARTED]
    clock.now = GRACE
    assert tracker.poll() == [AgentEdge.WORK_STOPPED, AgentEdge.NEEDS_INPUT]


def test_stale_session_is_dropped_silently(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 899.0
    assert tracker.poll() == []

    clock.now = 900.0
    assert tracker.poll() == [AgentEdge.WORK_STOPPED]
    assert not tracker.has_sessions


def test_events_keep_a_long_run_fresh(tracker, clock) -> None:
    tracker.record("working", A)
    for minute in range(1, 40):
        clock.now = minute * 60.0
        tracker.record("activity", A)
        assert tracker.poll() == []
    assert tracker.working


@pytest.mark.parametrize(
    ("event", "token"),
    (
        ("WORKING", A),
        ("bogus", A),
        ("working", "0123"),
        ("working", A.upper()),
        ("working", "g" * 16),
        ("working", A + "0"),
        ("working", None),
    ),
)
def test_invalid_event_or_token_changes_nothing(tracker, event, token) -> None:
    assert tracker.record(event, token) == []
    assert not tracker.has_sessions


def test_session_cap_evicts_least_recently_seen(tracker, clock) -> None:
    tokens = [f"{index:016x}" for index in range(AgentActivityTracker.MAX_SESSIONS + 1)]
    for index, token in enumerate(tokens):
        clock.now = float(index)
        tracker.record("working", token)

    assert tracker.working
    # The evicted first session is unknown now: its finish is ignored.
    assert tracker.record("finished", tokens[0]) == []
    for token in tokens[1:-1]:
        assert tracker.record("ended", token) == []
    assert tracker.record("ended", tokens[-1]) == [AgentEdge.WORK_STOPPED]


def test_parallel_sessions_keep_working_until_last_stops(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("working", B)
    clock.now = 61.0

    assert tracker.record("finished", A) == [AgentEdge.FINISHED_LONG]
    assert tracker.working
    assert tracker.record("finished", B) == [
        AgentEdge.WORK_STOPPED,
        AgentEdge.FINISHED_LONG,
    ]


def test_waiting_session_does_not_stop_a_working_one(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("working", B)
    tracker.record("needs_input", B)
    clock.now = GRACE

    assert tracker.poll() == [AgentEdge.NEEDS_INPUT]
    assert tracker.working


def test_clear_forgets_everything(tracker) -> None:
    tracker.record("working", A)
    tracker.clear()

    assert not tracker.has_sessions
    assert not tracker.working
    assert tracker.record("working", A) == [AgentEdge.WORK_STARTED]


def test_module_is_display_free() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src" / "mochi" / "agent_activity.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("import gi", "from gi", "cairo", "mochi.presence"):
        assert forbidden not in source


def test_grace_is_long_enough_for_an_approved_command_to_start() -> None:
    # PostToolUse only arrives after an approved tool finishes, so the grace
    # for a bare PermissionRequest has to outlast typical quick commands.
    assert GRACE >= 45.0


def test_prompt_still_waiting_nudges_at_once(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 70.0

    assert tracker.record("prompt_waiting", A) == [
        AgentEdge.WORK_STOPPED,
        AgentEdge.NEEDS_INPUT,
    ]
    assert not tracker.working
    assert tracker.record("prompt_waiting", A) == []
    clock.now = 70.0 + 2 * GRACE
    assert tracker.poll() == []


def test_prompt_still_waiting_after_needs_input_does_not_nudge_twice(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("needs_input", A)
    clock.now = 6.0

    assert tracker.record("prompt_waiting", A) == [
        AgentEdge.WORK_STOPPED,
        AgentEdge.NEEDS_INPUT,
    ]
    clock.now = 6.0 + GRACE
    assert tracker.poll() == []


def test_answering_a_waiting_prompt_restarts_work_and_rearms_the_nudge(tracker, clock) -> None:
    tracker.record("working", A)
    tracker.record("prompt_waiting", A)
    clock.now = 30.0

    assert tracker.record("activity", A) == [AgentEdge.WORK_STARTED]
    assert tracker.record("prompt_waiting", A) == [
        AgentEdge.WORK_STOPPED,
        AgentEdge.NEEDS_INPUT,
    ]


def test_prompt_waiting_from_an_unknown_session_nudges_without_starting_work(tracker) -> None:
    assert tracker.record("prompt_waiting", A) == [AgentEdge.NEEDS_INPUT]
    assert tracker.has_sessions
    assert not tracker.working


def test_finish_after_a_waiting_prompt_never_celebrates(tracker, clock) -> None:
    tracker.record("working", A)
    clock.now = 100.0
    tracker.record("prompt_waiting", A)

    assert tracker.record("finished", A) == []


def test_each_prompt_starts_a_fresh_run(tracker, clock) -> None:
    # An interrupted Claude Code turn sends no Stop; the next prompt's quick
    # finish must not be measured from the abandoned turn.
    tracker.record("working", A)
    clock.now = 120.0
    tracker.record("working", A)
    clock.now = 125.0

    assert tracker.record("finished", A) == [AgentEdge.WORK_STOPPED]
