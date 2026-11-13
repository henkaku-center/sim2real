"""Sound-driven controllers on the built-in test signal (sim/sound_motion.py)."""

import numpy as np
import pytest

from sim import sound_motion as sm


@pytest.fixture(scope="module")
def signal():
    return sm.test_signal(seed=0)


@pytest.fixture(scope="module")
def result(signal):
    audio, sections = signal
    return sm.simulate(audio, sections, seed=0)


def test_onsets_follow_the_clicks(signal):
    audio, _ = signal
    t = sm.features(audio).onset_times
    assert not ((t < 4) | ((t >= 26))).any()  # nothing in silence
    beat120 = t[(t >= 4) & (t < 12)]
    assert len(beat120) == 16
    assert np.allclose(np.diff(beat120), 0.5, atol=0.03)
    beat90 = t[(t >= 12) & (t < 20)]
    assert np.allclose(np.diff(beat90), 2 / 3, atol=0.03)


def test_deterministic(signal, result):
    audio, sections = signal
    _, again, _ = sm.simulate(audio, sections, seed=0)
    for a, b in zip(again, result[1]):
        assert np.array_equal(a.q, b.q) and np.array_equal(a.torso, b.torso), a.mode


def test_everyone_stands_still_before_the_sound_and_never_falls(result):
    _, _, table = result
    for mode, per in table.items():
        assert per["silence"]["still"] == 1.0, mode
        assert min(s["upright"] for s in per.values()) > 0.9, mode


def test_cpg_entrains_to_the_beat_and_keeps_its_gait(result):
    _, _, table = result
    cpg = table["cpg"]
    for label, hz in (("beat 120", 2.0), ("beat 90", 1.5)):
        assert cpg[label]["motion_hz"] == pytest.approx(hz, abs=0.15), label
        assert cpg[label]["beat_plv"] > 0.7, label
        assert cpg[label]["periodic"] > 0.8, label
        assert cpg[label]["flatness"] < 0.1, label


def test_cpg_switches_gait_with_tempo(result):
    _, runs, _ = result
    gaits = [g for _, _, g in next(r for r in runs if r.mode == "cpg").log]
    at = lambda s: gaits[int(s * sm.FRAME_HZ)]  # noqa: E731
    assert at(11) == "trot" and at(19) == "sway"


def test_dep_writhes_where_cpg_does_not(result):
    """The finding, pinned: DEP's motion is broadband and weakly periodic."""
    _, _, table = result
    for label in ("beat 120", "beat 90"):
        dep, cpg = table["dep"][label], table["cpg"][label]
        assert dep["flatness"] > 3 * cpg["flatness"], label
        assert dep["periodic"] < cpg["periodic"] - 0.2, label


def test_wav_round_trip(tmp_path):
    audio, _ = sm.test_signal(seed=1)
    path = tmp_path / "x.wav"
    sm.write_wav(path, audio[: sm.SR])
    back = sm.load_wav(path)
    assert len(back) == sm.SR
    assert np.abs(back - audio[: sm.SR]).max() < 1e-3
