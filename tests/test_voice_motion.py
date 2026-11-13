"""Voice-driven CPG on the synthetic voice (sim/voice_motion.py); no `say` needed."""

import math

import numpy as np
import pytest

from sim import voice_motion as vm
from sim.sound_motion import SR


@pytest.fixture(scope="module")
def scene():
    return vm.build_scene(synth=True, seed=0)


@pytest.fixture(scope="module")
def result(scene):
    return vm.simulate(*scene, seed=0)


def test_f0_tracks_a_harmonic_tone():
    t = np.arange(SR) / SR
    tone = 0.3 * sum(np.sin(2 * math.pi * 200 * h * t) / h for h in range(1, 6))
    f0 = vm.f0_track(tone.astype(np.float32))
    assert np.isfinite(f0[2:-2]).all()
    assert np.median(f0[2:-2]) == pytest.approx(200, rel=0.02)


def test_prosody_separates_calm_from_excited(scene):
    audio, utts, _ = scene
    p = vm.prosody(audio)
    by_style = {}
    for u in utts:
        a, b = int(u.start * vm.FRAME_HZ), int(u.end * vm.FRAME_HZ)
        by_style.setdefault(u.style, []).append((np.nanmedian(p.pitch_st[a:b]), p.slope[a:b].mean()))
    calm, excited = np.array(by_style["calm"]), np.array(by_style["excited"])
    assert (excited[:, 0] > 6).all() and (calm[:, 0] < 0).all()  # semitones re 220 Hz
    assert (excited[:, 1] > 0).all() and (calm[:, 1] < 0).all()  # rising vs falling


def test_keywords_map_to_intents():
    assert vm.understand("落ち着いて！").name == "settle"
    assert vm.understand("おいで。").name == "approach"
    assert vm.understand("あそぼう！").name == "play"
    assert vm.understand("こんにちは") is None


def test_deterministic(scene, result):
    _, again, _ = vm.simulate(*scene, seed=0)
    for a, b in zip(again, result[1]):
        assert np.array_equal(a.q, b.q), a.mode


def test_shouted_calm_down_settles_later_than_quiet_calm_down(result):
    both = result[2]["both"]
    quiet, shouted = both["calm down, calm"], both["calm down, excited"]
    assert quiet["settle_s"] < 1.0 and quiet["rebounds"] == 0
    assert shouted["settle_s"] > quiet["settle_s"] + 1.0
    assert shouted["rebounds"] >= 1


def test_words_alone_settle_either_way_and_prosody_alone_never_does(result):
    table = result[2]
    assert table["words"]["calm down, excited"]["settle_s"] < 1.5
    assert math.isnan(table["prosody"]["calm down, excited"]["settle_s"])


def test_words_choose_what_prosody_scales_how_much(result):
    table = result[2]
    come_calm = table["both"]["come, calm"]["amp_deg"]
    assert come_calm < 0.7 * table["words"]["come, calm"]["amp_deg"]  # quiet "come" walks smaller
    assert table["prosody"]["come, calm"]["amp_deg"] < 3  # without words, a quiet voice barely moves it
    assert table["both"]["come, excited"]["amp_deg"] > 2 * come_calm
    assert all(min(r.upright) > 0.9 for r in result[1])
