import numpy as np

from src.audio_dsp import MusicAnalyzer


def test_sensitivity_changes_spectrum_bands_and_onset_gain():
    sample_rate = 44100
    t = np.arange(1024, dtype=np.float32) / sample_rate
    samples = (
        0.18 * np.sin(2 * np.pi * 70 * t)
        + 0.12 * np.sin(2 * np.pi * 440 * t)
        + 0.08 * np.sin(2 * np.pi * 5200 * t)
    ).astype(np.float32)

    quiet = MusicAnalyzer(samplerate=sample_rate, blocksize=len(samples), sensitivity=0.4)
    strong = MusicAnalyzer(samplerate=sample_rate, blocksize=len(samples), sensitivity=2.5)
    quiet_state = quiet.process_samples(samples, now=1.0)
    strong_state = strong.process_samples(samples, now=1.0)

    assert float(np.mean(strong_state.bands)) > float(np.mean(quiet_state.bands))
    assert np.all(strong_state.bands >= quiet_state.bands)
    assert np.max(strong_state.bands) <= 1.0
    assert 0.0 <= strong_state.onset <= 1.0
