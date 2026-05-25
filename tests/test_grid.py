from unittest.mock import MagicMock

import ifcopenshell
import pytest

from vectorworks_plugin_import_ifc_homeskz.grid import (
    CLASS_X,
    CLASS_Y,
    determine_class,
    resolve_lines,
)


def make_ifc_model(*axes):
    """テスト用 ifcopenshell ファイルオブジェクトを生成する。

    axes: ({'name': str, 'points': [(x, y), ...]}, ...)
    """
    ifc = ifcopenshell.file()
    for axis_def in axes:
        pts = [ifc.create_entity('IfcCartesianPoint', Coordinates=list(coords)) for coords in axis_def['points']]
        polyline = ifc.create_entity('IfcPolyline', Points=pts)
        ifc.create_entity('IfcGridAxis', AxisTag=axis_def['name'], AxisCurve=polyline, SameSense=True)
    return ifc


class TestResolveLines:
    def test_resolves_line_coordinates(self):
        ifc = make_ifc_model(
            {'name': 'Y1', 'points': [(0.0, 0.0), (1000.0, 0.0)]},
            {'name': 'X1', 'points': [(500.0, 0.0), (500.0, 1000.0)]},
        )
        lines, _, _ = resolve_lines(ifc)
        coords = [(x1, y1, x2, y2) for x1, y1, x2, y2, _ in lines]
        assert (0.0, 0.0, 1000.0, 0.0) in coords
        assert (500.0, 0.0, 500.0, 1000.0) in coords

    def test_preserves_axis_name(self):
        ifc = make_ifc_model(
            {'name': 'Y1', 'points': [(0.0, 0.0), (1000.0, 0.0)]},
            {'name': 'X1', 'points': [(500.0, 0.0), (500.0, 1000.0)]},
        )
        lines, _, _ = resolve_lines(ifc)
        names = {name for *_, name in lines}
        assert 'X1' in names
        assert 'Y1' in names

    def test_deduplicates_identical_lines(self):
        ifc = make_ifc_model(
            {'name': 'A', 'points': [(0.0, 0.0), (1000.0, 0.0)]},
            {'name': 'B', 'points': [(0.0, 0.0), (1000.0, 0.0)]},
        )
        lines, _, _ = resolve_lines(ifc)
        assert len(lines) == 1

    def test_calculates_center(self):
        ifc = make_ifc_model(
            {'name': 'Y1', 'points': [(0.0, 0.0), (2000.0, 0.0)]},
            {'name': 'X1', 'points': [(1000.0, -1000.0), (1000.0, 1000.0)]},
        )
        _, center_x, center_y = resolve_lines(ifc)
        assert center_x == pytest.approx(1000.0)
        assert center_y == pytest.approx(0.0)

    def test_returns_zero_center_when_no_axes(self):
        ifc = ifcopenshell.file()
        lines, center_x, center_y = resolve_lines(ifc)
        assert lines == []
        assert center_x == 0.0
        assert center_y == 0.0

    def test_skips_none_axis_curve(self):
        axis = MagicMock()
        axis.AxisTag = 'X1'
        axis.AxisCurve = None
        ifc = MagicMock()
        ifc.by_type.return_value = [axis]
        lines, _, _ = resolve_lines(ifc)
        assert lines == []

    def test_skips_non_polyline_curve(self):
        axis = MagicMock()
        axis.AxisTag = 'X1'
        curve = MagicMock()
        curve.is_a.return_value = False
        axis.AxisCurve = curve
        ifc = MagicMock()
        ifc.by_type.return_value = [axis]
        lines, _, _ = resolve_lines(ifc)
        assert lines == []


class TestDetermineClass:
    def test_x_prefix_uppercase(self):
        assert determine_class('X1', 0, 0, 0, 1000) == CLASS_X

    def test_x_prefix_lowercase(self):
        assert determine_class('x2', 0, 0, 0, 1000) == CLASS_X

    def test_y_prefix_uppercase(self):
        assert determine_class('Y1', 0, 0, 1000, 0) == CLASS_Y

    def test_y_prefix_lowercase(self):
        assert determine_class('y2', 0, 0, 1000, 0) == CLASS_Y

    def test_vertical_line_becomes_x_class(self):
        # |Δx| < |Δy| → X通り
        assert determine_class('A', 500, 0, 500, 1000) == CLASS_X

    def test_horizontal_line_becomes_y_class(self):
        # |Δx| >= |Δy| → Y通り
        assert determine_class('B', 0, 500, 1000, 500) == CLASS_Y

    def test_diagonal_line_follows_dominant_axis(self):
        # |Δx|=300, |Δy|=1000 → X通り
        assert determine_class('C', 0, 0, 300, 1000) == CLASS_X
        # |Δx|=1000, |Δy|=300 → Y通り
        assert determine_class('D', 0, 0, 1000, 300) == CLASS_Y


class TestImportGrids:
    """vs モジュールをモックして import_grids() の動作を検証する。"""

    def _make_vs_mock(self):
        vs_mock = MagicMock()
        vs_mock.Handle.return_value = object()
        vs_mock.GetObject.return_value = None
        vs_mock.LNewObj.return_value = None
        vs_mock.CreateCustomObjectPath.return_value = None
        return vs_mock

    def test_returns_drawn_count(self):
        from unittest.mock import patch as _patch

        vs_mock = self._make_vs_mock()
        ifc = make_ifc_model(
            {'name': 'X1', 'points': [(0.0, 1000.0), (5000.0, 1000.0)]},
            {'name': 'Y1', 'points': [(0.0, 0.0), (5000.0, 0.0)]},
        )

        with _patch.dict('sys.modules', {'vs': vs_mock}):
            import importlib

            import vectorworks_plugin_import_ifc_homeskz.grid as grid_module
            importlib.reload(grid_module)
            count = grid_module.import_grids(ifc)

        assert count == 2

    def test_no_lines_returns_zero(self):
        from unittest.mock import patch as _patch

        vs_mock = self._make_vs_mock()
        ifc = ifcopenshell.file()

        with _patch.dict('sys.modules', {'vs': vs_mock}):
            import importlib

            import vectorworks_plugin_import_ifc_homeskz.grid as grid_module
            importlib.reload(grid_module)
            count = grid_module.import_grids(ifc)

        assert count == 0
