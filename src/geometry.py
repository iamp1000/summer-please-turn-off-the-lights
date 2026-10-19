"""
2D Spatial LED Geometry Engine (inspired by universe1987/LEDGeometry).

Eliminates 1D start-to-end linear bias by mapping physical LED strip zones
to 2D Euclidean coordinates (x, y) in [-1.0, 1.0]^2.

Supports:
1. Topologies:
   - 'linear': Standard 1D horizontal bar
   - 'headboard_u': Bed headboard arch (left leg up, top horizontal span, right leg down)
   - 'perimeter_rect': 4-sided monitor/tv/desk perimeter
   - 'center_split': Two mirrored halves meeting in the middle
   - 'custom': User-defined normalized (x, y) coordinates

2. Coordinate Projections:
   - Radial Projection: r = sqrt((x - x0)^2 + (y - y0)^2) (for circular ripples & shockwaves)
   - Directional Projection: p = x*cos(theta) + y*sin(theta) (for angled tides, slopes, sweeps)
   - Polar Angle Projection: phi = atan2(y - y0, x - x0) (for rotating spirals & pinwheels)
"""

from __future__ import annotations
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np


class StripTopology:
    """Calculates and stores 2D (x, y) spatial coordinates for each IC zone."""

    def __init__(self, num_zones: int = 50, layout: str = "headboard_u", custom_coords: Optional[List[Tuple[float, float]]] = None):
        self.num_zones = max(1, num_zones)
        self.layout = layout.lower().strip()
        self.coords: List[Tuple[float, float]] = []

        if custom_coords and len(custom_coords) == self.num_zones:
            self.coords = [
                (float(max(-1.0, min(1.0, x))), float(max(-1.0, min(1.0, y))))
                for x, y in custom_coords
            ]
        else:
            self.coords = self._generate_topology_coords(self.num_zones, self.layout)

        # Precompute coordinate arrays for vectorized operations
        self.xs = np.array([c[0] for c in self.coords], dtype=np.float32)
        self.ys = np.array([c[1] for c in self.coords], dtype=np.float32)

    @staticmethod
    def _generate_topology_coords(n: int, layout: str) -> List[Tuple[float, float]]:
        """Generates normalized (x, y) coordinates in [-1.0, 1.0]^2."""
        if n == 1:
            return [(0.0, 0.0)]

        coords: List[Tuple[float, float]] = []

        if layout in ("linear", "horizontal"):
            # Straight horizontal strip: left (-1.0, 0) to right (1.0, 0)
            for i in range(n):
                x = -1.0 + 2.0 * (i / float(n - 1))
                coords.append((x, 0.0))

        elif layout in ("headboard_u", "u_shape", "arch"):
            # U-shaped Bed Headboard:
            # 1. Left leg going up (bottom-left to top-left): ~25% of ICs
            # 2. Top horizontal span (top-left to top-right): ~50% of ICs
            # 3. Right leg going down (top-right to bottom-right): ~25% of ICs
            n_left = int(round(n * 0.25))
            n_right = int(round(n * 0.25))
            n_top = n - n_left - n_right

            # 1. Left vertical leg going UP from y=-1.0 to y=0.8 at x=-0.9
            for i in range(n_left):
                t = i / max(1, n_left)
                coords.append((-0.9, -1.0 + t * 1.8))

            # 2. Top horizontal span going RIGHT from x=-0.9 to x=0.9 at y=0.8
            for i in range(n_top):
                t = i / max(1, n_top - 1)
                coords.append((-0.9 + t * 1.8, 0.8))

            # 3. Right vertical leg going DOWN from y=0.8 to y=-1.0 at x=0.9
            for i in range(n_right):
                t = (i + 1) / max(1, n_right)
                coords.append((0.9, 0.8 - t * 1.8))

        elif layout in ("perimeter_rect", "monitor", "tv"):
            # 4-sided perimeter rectangle around monitor or TV
            n_side = n // 4
            n_rem = n % 4
            sides = [n_side, n_side, n_side, n_side]
            for r in range(n_rem):
                sides[r] += 1

            # Bottom (left to right)
            for i in range(sides[0]):
                t = i / max(1, sides[0])
                coords.append((-0.8 + t * 1.6, -0.6))
            # Right (bottom to top)
            for i in range(sides[1]):
                t = i / max(1, sides[1])
                coords.append((0.8, -0.6 + t * 1.2))
            # Top (right to left)
            for i in range(sides[2]):
                t = i / max(1, sides[2])
                coords.append((0.8 - t * 1.6, 0.6))
            # Left (top to bottom)
            for i in range(sides[3]):
                t = i / max(1, sides[3])
                coords.append((-0.8, 0.6 - t * 1.2))

        elif layout in ("center_split", "center_out"):
            # Two symmetrical legs meeting at the center
            half = (n - 1) / 2.0
            for i in range(n):
                dist = abs(i - half) / max(1.0, half)
                side = -1.0 if i < half else 1.0
                coords.append((side * dist, 0.0))

        else:
            # Fallback linear
            for i in range(n):
                coords.append((-1.0 + 2.0 * (i / float(n - 1)), 0.0))

        return coords

    def radial_projection(self, center_x: float = 0.0, center_y: float = 0.0) -> np.ndarray:
        """
        Computes normalized radial distances r in [0.0, 1.0] from an arbitrary 2D origin.
        Used for circular ripples, acoustic shockwaves, and expanding concentric bubbles.
        """
        dx = self.xs - center_x
        dy = self.ys - center_y
        dists = np.sqrt(dx * dx + dy * dy)
        min_d = float(np.min(dists))
        max_d = float(np.max(dists))
        denom = max_d - min_d
        if denom < 1e-6:
            return np.zeros(self.num_zones, dtype=np.float32)
        return (dists - min_d) / denom

    def directional_projection(self, angle_deg: float = 0.0) -> np.ndarray:
        """
        Computes normalized 1D projections along an arbitrary 2D directional vector.
        Angle 0 = left-to-right (+X)
        Angle 90 = bottom-to-top (+Y, for rising flames/convection)
        Angle 180 = right-to-left (-X)
        Angle 270 = top-to-bottom (-Y, for rainfall/cascades)
        """
        rad = math.radians(angle_deg)
        dir_x = math.cos(rad)
        dir_y = math.sin(rad)
        projs = self.xs * dir_x + self.ys * dir_y
        min_p = float(np.min(projs))
        max_p = float(np.max(projs))
        denom = max_p - min_p
        if denom < 1e-6:
            return np.zeros(self.num_zones, dtype=np.float32)
        return (projs - min_p) / denom

    def polar_projection(self, center_x: float = 0.0, center_y: float = 0.0) -> np.ndarray:
        """
        Computes normalized polar angles phi in [0.0, 1.0] around a 2D center point.
        Used for rotating color wheels, vortexes, and angular spiral sweeps.
        """
        dx = self.xs - center_x
        dy = self.ys - center_y
        angles = np.arctan2(dy, dx)  # [-pi, pi]
        # Normalize to [0.0, 1.0]
        return ((angles / np.pi) * 0.5 + 0.5).astype(np.float32)


# Global default topology for L930 (Bed Headboard U-Shape)
_default_l930_topology = StripTopology(num_zones=50, layout="headboard_u")


def get_l930_topology() -> StripTopology:
    global _default_l930_topology
    return _default_l930_topology


def set_l930_topology_layout(layout: str) -> StripTopology:
    global _default_l930_topology
    _default_l930_topology = StripTopology(num_zones=50, layout=layout)
    return _default_l930_topology
