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


def test_responsive_grid_columns_follow_width_breakpoints():
    from src.window_layout import responsive_grid_columns

    assert responsive_grid_columns(320) == 1
    assert responsive_grid_columns(469) == 1
    assert responsive_grid_columns(470) == 2
    assert responsive_grid_columns(819) == 2
    assert responsive_grid_columns(820) == 3


def test_responsive_grid_columns_respect_grid_specific_cap():
    from src.window_layout import responsive_grid_columns

    assert responsive_grid_columns(1400, max_columns=2) == 2
    assert responsive_grid_columns(600, max_columns=2) == 2
    assert responsive_grid_columns(320, max_columns=2) == 1
    assert responsive_grid_columns(1400, max_columns=1) == 1
