"""Synthetic clock/phase fixtures only: no robot plans, channels or amplitudes."""
from dataclasses import FrozenInstanceError
import pytest

from sim.offline_load_lifecycle import OfflineLoadLifecycle, Phase, Plan, State


def synthetic_plan(name="synthetic"):
    # Arbitrary virtual-time test boundaries, NOT recommended hardware timings.
    return Plan(name, (Phase("fixture-a", 7), Phase("fixture-b", 9)), 12)


def test_prepare_and_poll_never_start_or_advance():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    assert run.poll(1000).state == State.PREPARED
    assert run.snapshot.phase_id is None
    assert run.start(token, 1000).phase_id == "fixture-a"
    assert run.poll(1006).completed_phases == 0
    assert run.snapshot.phase_id == "fixture-a"


def test_deliberate_completion_is_finite_and_sticky():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    run.start(token, 0)
    assert run.finish_phase(token, "fixture-a", 3).phase_id == "fixture-b"
    done = run.finish_phase(token, "fixture-b", 8)
    assert done.state == State.COMPLETE and done.completed_phases == 2
    assert done.phase_id is None
    assert run.poll(1000).state == State.COMPLETE
    assert run.abort().state == State.COMPLETE
    with pytest.raises(RuntimeError):
        run.start(token, 1000)


@pytest.mark.parametrize("started", [False, True])
def test_abort_discards_active_phase_and_prevents_resume(started):
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    if started:
        run.start(token, 0)
    assert run.abort().state == State.ABORTED
    assert run.snapshot.phase_id is None
    with pytest.raises(RuntimeError):
        run.start(token, 2)
    with pytest.raises(RuntimeError):
        run.finish_phase(token, "fixture-a", 2)
    assert run.poll(100).state == State.ABORTED


@pytest.mark.parametrize("running", [False, True])
def test_reset_drops_preparation_and_accepts_new_clock_epoch(running):
    run = OfflineLoadLifecycle()
    old = run.prepare(synthetic_plan())
    if running:
        run.start(old, 1000)
    reset = run.reset()
    assert reset.state == State.IDLE and reset.plan_id is None
    with pytest.raises(ValueError):
        run.start(old, 0)
    new = run.prepare(synthetic_plan())
    assert new != old
    assert run.start(new, 0).state == State.RUNNING
    with pytest.raises(ValueError):
        run.finish_phase(old, "fixture-a", 1)
    assert run.snapshot.completed_phases == 0


def test_phase_deadline_wins_over_completion():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    run.start(token, 0)
    assert run.poll(6).state == State.RUNNING
    expired = run.finish_phase(token, "fixture-a", 7)
    assert expired.state == State.TIMED_OUT and expired.reason == "phase timeout"
    assert expired.completed_phases == 0 and expired.phase_id is None
    assert run.poll(99).state == State.TIMED_OUT


def test_overall_deadline_is_not_extended_by_phase_progress():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    run.start(token, 100)
    run.finish_phase(token, "fixture-a", 106)
    assert run.poll(111).state == State.RUNNING
    expired = run.finish_phase(token, "fixture-b", 112)
    assert expired.state == State.TIMED_OUT and expired.reason == "plan timeout"
    assert expired.completed_phases == 1


def test_duplicate_out_of_order_and_cross_plan_events_do_not_advance():
    run = OfflineLoadLifecycle()
    old = run.prepare(synthetic_plan())
    run.start(old, 0)
    with pytest.raises(ValueError):
        run.finish_phase(old, "fixture-b", 1)
    with pytest.raises(RuntimeError):
        run.prepare(synthetic_plan("replacement"))
    run.finish_phase(old, "fixture-a", 2)
    with pytest.raises(ValueError):
        run.finish_phase(old, "fixture-a", 3)
    assert run.snapshot.completed_phases == 1
    run.abort()
    new = run.prepare(synthetic_plan("replacement"))
    run.start(new, 4)
    with pytest.raises(ValueError):
        run.finish_phase(old, "fixture-a", 5)
    assert run.snapshot.plan_id == "replacement" and run.snapshot.completed_phases == 0


@pytest.mark.parametrize("bad", [-1, True, 1.5, float("nan"), float("inf"), "1"])
def test_invalid_time_cannot_start(bad):
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    with pytest.raises(ValueError):
        run.start(token, bad)
    assert run.snapshot.state == State.PREPARED


def test_backward_clock_is_rejected_without_phase_change():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    run.start(token, 10)
    before = run.snapshot
    with pytest.raises(ValueError):
        run.finish_phase(token, "fixture-a", 9)
    assert run.snapshot == before


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, float("inf")])
def test_time_budget_must_be_explicit_positive_integer(bad):
    with pytest.raises(ValueError):
        Phase("fixture", bad)
    with pytest.raises(ValueError):
        Plan("fixture", (Phase("a", 1),), bad)


def test_plan_requires_finite_unique_phases_and_is_immutable():
    for phases in [(), [], [Phase("a", 1)], ("a",), (Phase("a", 1), Phase("a", 2))]:
        with pytest.raises(ValueError):
            Plan("fixture", phases, 10)
    for name in ["", " ", None]:
        with pytest.raises(ValueError):
            Phase(name, 1)
        with pytest.raises(ValueError):
            Plan(name, (Phase("a", 1),), 10)
    with pytest.raises(FrozenInstanceError):
        synthetic_plan().timeout_ms = 999


def test_identical_external_events_produce_identical_snapshots():
    def trace():
        run = OfflineLoadLifecycle()
        token = run.prepare(synthetic_plan())
        return [run.snapshot, run.start(token, 0), run.poll(2),
                run.finish_phase(token, "fixture-a", 4), run.abort(), run.reset()]
    assert trace() == trace()


def test_recreated_model_cannot_accept_previous_instances_ticket():
    previous = OfflineLoadLifecycle()
    old = previous.prepare(synthetic_plan())
    previous.start(old, 0)
    recreated = OfflineLoadLifecycle()
    new = recreated.prepare(synthetic_plan())
    assert old.generation == new.generation  # counters alone would collide
    with pytest.raises(ValueError):
        recreated.start(old, 0)
    assert recreated.start(new, 0).state == State.RUNNING
    with pytest.raises(ValueError):
        recreated.finish_phase(old, "fixture-a", 1)


def test_abort_does_not_require_clock_recovery():
    run = OfflineLoadLifecycle()
    token = run.prepare(synthetic_plan())
    run.start(token, 10)
    with pytest.raises(ValueError):
        run.poll(0)
    assert run.abort().state == State.ABORTED
    assert run.snapshot.phase_id is None
