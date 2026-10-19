"""
Unit tests for 2D Spatial LED Geometry Engine (StripTopology).
"""

import numpy as np
import pytest
from src.geometry import StripTopology, get_l930_topology, set_l930_topology_layout


def test_linear_topology():
    topo = StripTopology(num_zones=50, layout="linear")
    assert len(topo.coords) == 50
    assert len(topo.xs) == 50
    assert len(topo.ys) == 50

    # Start at -1.0, End at 1.0, y is 0.0
    assert pytest.approx(topo.coords[0][0], abs=1e-4) == -1.0
    assert pytest.approx(topo.coords[-1][0], abs=1e-4) == 1.0
    assert all(pytest.approx(y, abs=1e-4) == 0.0 for y in topo.ys)


def test_headboard_u_topology():
    topo = StripTopology(num_zones=50, layout="headboard_u")
    assert len(topo.coords) == 50

    # Left leg starts at bottom-left (-0.9, -1.0)
    assert pytest.approx(topo.coords[0][0], abs=0.05) == -0.9
    assert pytest.approx(topo.coords[0][1], abs=0.05) == -1.0

    # Peak in middle (top span) has y = 0.8
    mid_idx = 25
    assert pytest.approx(topo.coords[mid_idx][1], abs=0.05) == 0.8

    # Right leg ends at bottom-right (0.9, -1.0)
    assert pytest.approx(topo.coords[-1][0], abs=0.05) == 0.9
    assert pytest.approx(topo.coords[-1][1], abs=0.05) == -1.0


def test_perimeter_rect_topology():
    topo = StripTopology(num_zones=60, layout="perimeter_rect")
    assert len(topo.coords) == 60
    # Coordinates must stay within [-1.0, 1.0]
    assert np.all(topo.xs >= -1.0) and np.all(topo.xs <= 1.0)
    assert np.all(topo.ys >= -1.0) and np.all(topo.ys <= 1.0)


def test_radial_projection_bounds():
    topo = StripTopology(num_zones=50, layout="headboard_u")
    # Project from center top (0.0, 0.8)
    r = topo.radial_projection(center_x=0.0, center_y=0.8)
    assert len(r) == 50
    assert np.min(r) >= 0.0
    assert np.max(r) <= 1.0
    # The middle zone (near 0.0, 0.8) should have lowest radial distance
    mid_idx = 25
    assert r[mid_idx] < 0.2


def test_directional_projection_bounds():
    topo = StripTopology(num_zones=50, layout="headboard_u")
    # Angle 90 is bottom-to-top (+Y)
    y_proj = topo.directional_projection(angle_deg=90.0)
    assert len(y_proj) == 50
    assert np.min(y_proj) >= 0.0
    assert np.max(y_proj) <= 1.0
    # Bottom endpoints (zones 0 and 49) should have minimum Y projection
    assert y_proj[0] < 0.1
    assert y_proj[-1] < 0.1
    # Middle zone at the top should have maximum Y projection
    assert y_proj[25] > 0.9


def test_polar_projection_bounds():
    topo = StripTopology(num_zones=50, layout="headboard_u")
    phi = topo.polar_projection(center_x=0.0, center_y=0.0)
    assert len(phi) == 50
    assert np.min(phi) >= 0.0
    assert np.max(phi) <= 1.0


def test_global_topology_setter():
    set_l930_topology_layout("linear")
    t1 = get_l930_topology()
    assert t1.layout == "linear"

    set_l930_topology_layout("headboard_u")
    t2 = get_l930_topology()
    assert t2.layout == "headboard_u"
