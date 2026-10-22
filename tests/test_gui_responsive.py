from src.window_layout import responsive_window_geometry


def test_responsive_geometry_fits_large_display():
    width, height, x, y, min_width, min_height = responsive_window_geometry(1920, 1080)
    assert 0 <= x < 1920
    assert 0 <= y < 1080
    assert x + width <= 1920
    assert y + height <= 1080
    assert min_width <= width
    assert min_height <= height
    assert width > 540
    assert height > 600


def test_responsive_geometry_adapts_to_small_display():
    width, height, x, y, min_width, min_height = responsive_window_geometry(800, 600)
    assert x >= 0 and y >= 0
    assert x + width <= 800
    assert y + height <= 600
    assert min_width <= width
    assert min_height <= height


def test_responsive_geometry_handles_tiny_display_without_negative_sizes():
    width, height, x, y, min_width, min_height = responsive_window_geometry(320, 320)
    assert width > 0 and height > 0
    assert min_width > 0 and min_height > 0
    assert x >= 0 and y >= 0
