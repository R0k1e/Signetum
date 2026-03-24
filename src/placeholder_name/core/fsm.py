"""Task finite state machine.

Complex object lifecycles are modelled with the `transitions` library.
Illegal state jumps are blocked by the machine — no ad-hoc if/else branching.
"""

from enum import Enum
from typing import ClassVar

from transitions import Machine


class TaskState(Enum):
    """All legal task states."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskFSM:
    """Models a task lifecycle as an explicit FSM.

    Transitions:
        PENDING  --start-->   RUNNING
        RUNNING  --complete-> DONE
        RUNNING  --fail-->    FAILED
    """

    _states: ClassVar[list[str]] = [s.value for s in TaskState]
    _transitions: ClassVar[list[dict[str, str]]] = [
        {
            "trigger": "start",
            "source": TaskState.PENDING.value,
            "dest": TaskState.RUNNING.value,
        },
        {
            "trigger": "complete",
            "source": TaskState.RUNNING.value,
            "dest": TaskState.DONE.value,
        },
        {
            "trigger": "fail",
            "source": TaskState.RUNNING.value,
            "dest": TaskState.FAILED.value,
        },
    ]

    def __init__(self) -> None:
        self._machine = Machine(
            model=self,
            states=self._states,
            transitions=self._transitions,
            initial=TaskState.PENDING.value,
        )

    @property
    def current_state(self) -> TaskState:
        """Return the current state as a typed enum value."""
        return TaskState(self.state)  # type: ignore[attr-defined]
