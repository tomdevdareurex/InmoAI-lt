from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.geo import flag_coordinates

_VILNIUS_BBOX = {"lat_min": 54.50, "lat_max": 54.90, "lon_min": 24.95, "lon_max": 25.55}
_LITHUANIA_BBOX = {"lat_min": 53.8, "lat_max": 56.5, "lon_min": 20.8, "lon_max": 26.9}


class TestFlagCoordinates:
    def test_inside_vilnius_no_flags(self):
        df = pd.DataFrame(
            {
                "latitude": [54.68],
                "longitude": [25.27],
                "coordinate_precision": [None],
            }
        )
        out = flag_coordinates(df, _VILNIUS_BBOX, _LITHUANIA_BBOX)
        assert bool(out.loc[0, "flag_coords_outside_vilnius"]) is False
        assert bool(out.loc[0, "flag_coords_outside_lithuania"]) is False

    def test_outside_vilnius_but_inside_lithuania(self):
        df = pd.DataFrame(
            {
                "latitude": [55.7],  # Kaunas-ish, inside Lithuania, outside Vilnius bbox
                "longitude": [24.0],
                "coordinate_precision": [None],
            }
        )
        out = flag_coordinates(df, _VILNIUS_BBOX, _LITHUANIA_BBOX)
        assert bool(out.loc[0, "flag_coords_outside_vilnius"]) is True
        assert bool(out.loc[0, "flag_coords_outside_lithuania"]) is False

    def test_outside_lithuania(self):
        df = pd.DataFrame(
            {"latitude": [10.0], "longitude": [10.0], "coordinate_precision": [None]}
        )
        out = flag_coordinates(df, _VILNIUS_BBOX, _LITHUANIA_BBOX)
        assert bool(out.loc[0, "flag_coords_outside_lithuania"]) is True

    def test_approximate_precision_flag(self):
        df = pd.DataFrame(
            {
                "latitude": [54.68, 54.68],
                "longitude": [25.27, 25.27],
                "coordinate_precision": ["approximate", None],
            }
        )
        out = flag_coordinates(df, _VILNIUS_BBOX, _LITHUANIA_BBOX)
        assert bool(out.loc[0, "flag_coords_approximate"]) is True
        assert bool(out.loc[1, "flag_coords_approximate"]) is False
        assert "coordinate_precision" not in out.columns

    def test_coordinates_rounded_to_6dp(self):
        df = pd.DataFrame(
            {
                "latitude": [54.123456789],
                "longitude": [25.987654321],
                "coordinate_precision": [None],
            }
        )
        out = flag_coordinates(df, _VILNIUS_BBOX, _LITHUANIA_BBOX)
        assert out.loc[0, "latitude"] == 54.123457
        assert out.loc[0, "longitude"] == 25.987654
