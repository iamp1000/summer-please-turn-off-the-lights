"""
Tests for LumiSync-inspired enhancements:
- MasterVolumeProbe (Windows Core Audio loopback compensation)
- ArtworkPaletteProvider (Windows Media GSMTC thumbnail palette extraction)
- Spectral Complexity (Shannon entropy in MusicAnalyzer)
- Spatial Reaction Styles: BassBounceStyle, CenterBurstStyle, TwinkleStyle
"""

import io
import math
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.audio_dsp import MusicAnalyzer, MusicState, Section
from src.master_volume import MasterVolumeProbe
from src.artwork_sync import ArtworkPaletteProvider, extract_palette_from_bytes
from src.visual_styles import (
    BassBounceStyle,
    CenterBurstStyle,
    TwinkleStyle,
    create_style_instances,
    get_visual_style,
    STYLE_REGISTRY,
)


class TestMasterVolumeProbe:
    def test_compensate_samples_linear(self):
        probe = MasterVolumeProbe()
        probe._available = True
        mock_endpoint = MagicMock()
        mock_endpoint.GetMute.return_value = 0
        # -6 dB is approx 0.501187 linear gain
        mock_endpoint.GetMasterVolumeLevel.return_value = -6.0
        probe._endpoint = mock_endpoint

        gain = probe.linear_gain()
        assert gain is not None
        assert math.isclose(gain, 0.501187, rel_tol=1e-3)

        samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        compensated = probe.compensate_samples(samples)
        # Should be boosted by approx 1 / 0.501187 ~= 1.995
        assert math.isclose(compensated[0], 0.1 / gain, rel_tol=1e-3)

    def test_compensate_samples_muted_or_full(self):
        probe = MasterVolumeProbe()
        probe._available = True
        mock_endpoint = MagicMock()
        mock_endpoint.GetMute.return_value = 1
        probe._endpoint = mock_endpoint

        assert probe.linear_gain() == 0.0
        samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        # When muted (gain=0.0 <= 1e-4), should return untouched samples without div-by-zero
        compensated = probe.compensate_samples(samples)
        assert np.array_equal(samples, compensated)


class TestArtworkPaletteProvider:
    def test_fallback_when_empty(self):
        provider = ArtworkPaletteProvider()
        provider._cached_palette = None
        # With no media player running or empty thumbnail, get_palette() should return None or fallback
        pal = provider.get_palette()
        assert pal is None or isinstance(pal, list)

    def test_color_extraction_math(self):
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(255, 120, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        bytes_data = buf.getvalue()

        palette = extract_palette_from_bytes(bytes_data, color_count=4)
        assert len(palette) >= 1
        h, s, v = palette[0]
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100


class TestSpectralComplexity:
    def test_entropy_computation(self):
        analyzer = MusicAnalyzer(samplerate=44100, blocksize=512)

        # 1. Flat white noise -> high complexity
        np.random.seed(42)
        noise = np.random.uniform(-0.5, 0.5, 4096).astype(np.float32)
        st_noise = analyzer.process_samples(noise)
        assert hasattr(st_noise, "complexity")
        assert st_noise.complexity > 0.50

        # 2. Pure sine wave (concentrated in single band) -> low complexity
        t = np.linspace(0, 4096 / 44100.0, 4096, endpoint=False)
        sine = (np.sin(2 * np.pi * 440 * t) * 0.8).astype(np.float32)
        st_sine = analyzer.process_samples(sine)
        assert st_sine.complexity < st_noise.complexity


class TestSpatialReactionStyles:
    def test_bass_bounce_50_zones(self):
        style = BassBounceStyle()
        st = MusicState(
            bands=np.array([1.0, 0.9, 0.8, 0.1, 0.05, 0.05, 0.01, 0.01], dtype=np.float32),
            kick=0.9,
            energy=0.8,
            silent=False,
            section=Section.DROP,
            palette=[(320, 90, 80), (180, 85, 75)],
        )
        frame = style.render(st, dt=0.033, num_zones=50)
        assert len(frame) == 50
        # Outer ends (0 and 49) should be active and illuminated
        assert frame[0][2] > 20
        assert frame[49][2] > 20
        # Color values must be in valid Tapo HSV range
        for h, s, v in frame:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100

    def test_bass_bounce_single_zone(self):
        style = BassBounceStyle()
        st = MusicState(kick=0.8, energy=0.7, silent=False, section=Section.DROP)
        frame = style.render(st, dt=0.033, num_zones=1)
        assert len(frame) == 1
        assert frame[0][2] > 0

    def test_center_burst_propagation(self):
        style = CenterBurstStyle()
        st = MusicState(
            kick=0.9,
            onset=0.85,
            energy=0.8,
            silent=False,
            section=Section.DROP,
            beat_phase=0.5,
            palette=[(280, 85, 80), (120, 80, 75)],
        )
        # Step 1: Center hit
        f1 = style.render(st, dt=0.033, num_zones=50)
        assert len(f1) == 50
        left_center = 24
        right_center = 25
        assert f1[left_center][2] > 20
        assert f1[right_center][2] > 20

        # Step 2: Next frame outward shift
        st_decay = MusicState(kick=0.0, onset=0.0, energy=0.5, silent=False, section=Section.DROP, beat_phase=0.6)
        f2 = style.render(st_decay, dt=0.033, num_zones=50)
        assert len(f2) == 50
        # Adjacent zones should have received the outward ripple
        assert f2[left_center - 1][2] > 0
        assert f2[right_center + 1][2] > 0

    def test_twinkle_sparkle(self):
        style = TwinkleStyle()
        st = MusicState(
            hat=0.85,
            onset=0.7,
            energy=0.6,
            silent=False,
            section=Section.DROP,
            palette=[(200, 70, 70), (45, 80, 80)],
        )
        frame = style.render(st, dt=0.033, num_zones=50)
        assert len(frame) == 50
        # Some zones should have bright sparkle pops
        max_v = max(c[2] for c in frame)
        assert max_v >= 50

    def test_silence_handling(self):
        silent_st = MusicState(silent=True, energy=0.0, section=Section.SILENT)
        for cls in (BassBounceStyle, CenterBurstStyle, TwinkleStyle):
            style = cls()
            f = style.render(silent_st, dt=0.033, num_zones=50)
            assert all(c == (0, 0, 0) for c in f)

    def test_style_registry_instances(self):
        reg = create_style_instances()
        assert "bass_bounce" in reg
        assert "center_burst" in reg
        assert "twinkle" in reg
        assert isinstance(reg["bass_bounce"], BassBounceStyle)
        assert isinstance(reg["center_burst"], CenterBurstStyle)
        assert isinstance(reg["twinkle"], TwinkleStyle)
