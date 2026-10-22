"""Pure helpers for responsive desktop window sizing."""


def responsive_window_geometry(
    screen_width: int, screen_height: int
) -> tuple[int, int, int, int, int, int]:
    """Return width, height, x, y, min_width and min_height for the current screen.

    The initial window uses a proportion of the available display area. Minimum
    dimensions also shrink on small displays, while the native window remains
    user-resizable after it opens.
    """
    sw = max(320, int(screen_width))
    sh = max(320, int(screen_height))
    margin_x = max(12, min(28, int(sw * 0.018)))
    margin_y = max(18, min(36, int(sh * 0.035)))
    available_w = max(280, sw - 2 * margin_x)
    available_h = max(300, sh - 2 * margin_y)
    min_w = min(560, available_w)
    min_h = min(600, available_h)
    width = min(available_w, max(min_w, int(sw * 0.86)))
    height = min(available_h, max(min_h, int(sh * 0.88)))
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    return width, height, x, y, min_w, min_h


def responsive_grid_columns(width: int, max_columns: int = 3) -> int:
    """Choose a readable grid column count from available pixels and a per-grid cap."""
    available = max(1, int(width))
    cap = max(1, min(3, int(max_columns)))
    fitted = 1 if available < 470 else (2 if available < 820 else 3)
    return min(cap, fitted)
