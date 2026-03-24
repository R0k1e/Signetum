"""Property-based tests for core domain logic.

Uses Hypothesis to stress-test corner cases rather than hand-crafted examples.
Tests behaviour, not implementation details.
"""

import icontract
import pytest
from hypothesis import given
from hypothesis import strategies as st
from transitions import MachineError

from placeholder_name.core.fsm import TaskFSM
from placeholder_name.core.fsm import TaskState
from placeholder_name.core.service import GreeterService

_service = GreeterService()


# ---------------------------------------------------------------------------
# GreeterService — property tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
@given(name=st.text(min_size=1).filter(lambda s: s.strip()))
def test_greet_always_starts_with_hello(name: str) -> None:
    result = _service.greet(name)
    assert result.startswith("Hello")


@pytest.mark.slow
@given(name=st.text(min_size=1).filter(lambda s: s.strip()))
def test_greet_contains_stripped_name(name: str) -> None:
    result = _service.greet(name)
    assert name.strip() in result


def test_greet_rejects_empty_name() -> None:
    with pytest.raises(icontract.ViolationError):
        _service.greet("")


def test_greet_rejects_whitespace_only_name() -> None:
    with pytest.raises(icontract.ViolationError):
        _service.greet("   ")


# ---------------------------------------------------------------------------
# TaskFSM — state machine tests
# ---------------------------------------------------------------------------

def test_fsm_initial_state_is_pending() -> None:
    fsm = TaskFSM()
    assert fsm.current_state is TaskState.PENDING


def test_fsm_pending_to_running() -> None:
    fsm = TaskFSM()
    fsm.start()  # type: ignore[attr-defined]  # transitions injects trigger methods
    assert fsm.current_state is TaskState.RUNNING


def test_fsm_running_to_done() -> None:
    fsm = TaskFSM()
    fsm.start()  # type: ignore[attr-defined]
    fsm.complete()  # type: ignore[attr-defined]
    assert fsm.current_state is TaskState.DONE


def test_fsm_running_to_failed() -> None:
    fsm = TaskFSM()
    fsm.start()  # type: ignore[attr-defined]
    fsm.fail()  # type: ignore[attr-defined]
    assert fsm.current_state is TaskState.FAILED


def test_fsm_illegal_transition_raises() -> None:
    """Verify FSM blocks illegal state jumps — no direct PENDING → DONE."""
    fsm = TaskFSM()
    with pytest.raises((MachineError, AttributeError)):
        fsm.complete()  # type: ignore[attr-defined]
