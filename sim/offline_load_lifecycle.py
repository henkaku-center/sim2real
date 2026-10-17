"""Offline load-test control-flow model. NOT an actuator or firmware entry point.

Plans contain only externally supplied opaque phase identifiers and time budgets.
No angles, channels, calibration, hardware transport, clock, callbacks or default
motion plan live here. A completed mock phase is not physical acceptance.
"""
from dataclasses import dataclass
from enum import Enum


def _positive_integer(value: int) -> bool:
    return type(value) is int and value > 0


@dataclass(frozen=True)
class Phase:
    phase_id: str
    timeout_ms: int

    def __post_init__(self):
        if not isinstance(self.phase_id, str) or not self.phase_id.strip():
            raise ValueError("phase_id must be a nonempty string")
        if not _positive_integer(self.timeout_ms):
            raise ValueError("phase timeout must be a positive integer")


@dataclass(frozen=True)
class Plan:
    plan_id: str
    phases: tuple[Phase, ...]
    timeout_ms: int

    def __post_init__(self):
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise ValueError("plan_id must be a nonempty string")
        if type(self.phases) is not tuple or not self.phases:
            raise ValueError("phases must be a finite, nonempty tuple")
        if any(type(phase) is not Phase for phase in self.phases):
            raise ValueError("each phase must be a Phase")
        ids = [phase.phase_id for phase in self.phases]
        if len(set(ids)) != len(ids):
            raise ValueError("phase identifiers must be unique within a plan")
        if not _positive_integer(self.timeout_ms):
            raise ValueError("plan timeout must be a positive integer")


class State(str, Enum):
    IDLE = "idle"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETE = "complete"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class Snapshot:
    state: State
    generation: int
    plan_id: str | None
    phase_id: str | None
    completed_phases: int
    reason: str


@dataclass(frozen=True, eq=False)
class PreparedPlan:
    """In-memory ticket, valid only for the instance/preparation which issued it."""
    generation: int


class OfflineLoadLifecycle:
    """Deterministic, in-memory model; never interprets phase identifiers.

    The caller supplies a monotonic integer clock. Reset models a new clock
    epoch and discards preparation; a stale generation cannot start/advance a
    replacement plan. A running phase advances only on explicit completion.
    Timeouts win over completion at the deadline. Terminal states are sticky.
    """

    def __init__(self):
        self._generation = 0
        self.reset()

    def reset(self) -> Snapshot:
        self._generation += 1
        self._state = State.IDLE
        self._ticket: PreparedPlan | None = None
        self._plan: Plan | None = None
        self._completed = 0
        self._last_ms: int | None = None
        self._started_ms: int | None = None
        self._phase_started_ms: int | None = None
        self._reason = "reset; preparation discarded"
        return self.snapshot

    @property
    def snapshot(self) -> Snapshot:
        phase = (self._plan.phases[self._completed].phase_id
                 if self._state == State.RUNNING else None)
        return Snapshot(self._state, self._generation,
                        self._plan.plan_id if self._plan else None,
                        phase, self._completed, self._reason)

    def prepare(self, plan: Plan) -> PreparedPlan:
        if type(plan) is not Plan:
            raise ValueError("an explicit Plan is required")
        if self._state in (State.PREPARED, State.RUNNING):
            raise RuntimeError("abort or reset before replacing an active plan")
        self._generation += 1
        self._ticket = PreparedPlan(self._generation)
        self._plan = plan
        self._completed = 0
        self._started_ms = self._phase_started_ms = None
        self._state = State.PREPARED
        self._reason = "prepared; awaiting explicit start"
        return self._ticket

    def _check_time(self, now_ms: int):
        if type(now_ms) is not int or now_ms < 0:
            raise ValueError("time must be a nonnegative integer")
        if self._last_ms is not None and now_ms < self._last_ms:
            raise ValueError("time must be monotonic; reset starts a new epoch")
        self._last_ms = now_ms

    def _require(self, ticket: PreparedPlan, state: State):
        if ticket is None or ticket is not self._ticket:
            raise ValueError("stale or invalid preparation ticket")
        if self._state != state:
            raise RuntimeError(f"operation requires {state.value}")

    def start(self, ticket: PreparedPlan, now_ms: int) -> Snapshot:
        self._require(ticket, State.PREPARED)
        self._check_time(now_ms)
        self._started_ms = self._phase_started_ms = now_ms
        self._state = State.RUNNING
        self._reason = "mock run started"
        return self.snapshot

    def poll(self, now_ms: int) -> Snapshot:
        self._check_time(now_ms)
        if self._state == State.RUNNING:
            if now_ms - self._started_ms >= self._plan.timeout_ms:
                self._state, self._reason = State.TIMED_OUT, "plan timeout"
            elif now_ms - self._phase_started_ms >= self._plan.phases[self._completed].timeout_ms:
                self._state, self._reason = State.TIMED_OUT, "phase timeout"
        return self.snapshot

    def finish_phase(self, ticket: PreparedPlan, phase_id: str, now_ms: int) -> Snapshot:
        self._require(ticket, State.RUNNING)
        # A late acknowledgement must never beat a deadline or start another phase.
        if self.poll(now_ms).state == State.TIMED_OUT:
            return self.snapshot
        if phase_id != self._plan.phases[self._completed].phase_id:
            raise ValueError("completion does not match the current phase")
        self._completed += 1
        if self._completed == len(self._plan.phases):
            self._state, self._reason = State.COMPLETE, "all mock phases completed"
        else:
            self._phase_started_ms = now_ms
        return self.snapshot

    def abort(self) -> Snapshot:
        # Cancellation must not depend on a working/monotonic clock.
        if self._state in (State.PREPARED, State.RUNNING):
            self._state, self._reason = State.ABORTED, "operator abort"
        return self.snapshot
