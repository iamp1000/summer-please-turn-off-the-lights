from __future__ import annotations

from types import SimpleNamespace

from src.audio_dsp import DynamicSongCalibrator
from src.music_dynamics import music_is_genuinely_active


def test_quiet_but_real_loopback_audio_becomes_active():
    calibrator = DynamicSongCalibrator(sensitivity=1.0)
    result = None

    # A quiet signal above the absolute-silence gate should not remain dark
    # because the calibrator starts with loud-song percentile defaults.
    for index in range(32):
        result = calibrator.update(
            rms=0.004,
            kick=0.0,
            now=100.0 + index * 0.025,
            dt=0.025,
        )

    assert result is not None
    energy, _trend, _drop, silent = result
    assert silent is False
    assert energy >= 0.015
    assert music_is_genuinely_active(SimpleNamespace(silent=silent, energy=energy))


def test_absolute_silence_stays_inactive():
    calibrator = DynamicSongCalibrator(sensitivity=1.0)
    for index in range(32):
        energy, _trend, _drop, silent = calibrator.update(
            rms=0.0,
            kick=0.0,
            now=200.0 + index * 0.025,
            dt=0.025,
        )

    assert silent is True
    assert energy == 0.0
    assert not music_is_genuinely_active(SimpleNamespace(silent=True, energy=energy))


def test_music_active_gate_accepts_low_normalized_energy_but_rejects_noise():
    assert music_is_genuinely_active(SimpleNamespace(silent=False, energy=0.02))
    assert not music_is_genuinely_active(SimpleNamespace(silent=False, energy=0.01))
    assert not music_is_genuinely_active(SimpleNamespace(silent=True, energy=0.8))
