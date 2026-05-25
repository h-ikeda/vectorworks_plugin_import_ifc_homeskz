import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from vw_import_ifc_homeskz.grid import (
    CLASS_X,
    CLASS_Y,
    determine_class,
    parse_ifc_content,
    resolve_lines,
)

# --- サンプル IFC コンテンツ ---

SAMPLE_IFC = """\
#1 = IFCCARTESIANPOINT((0.,1000.));
#2 = IFCCARTESIANPOINT((5000.,1000.));
#3 = IFCCARTESIANPOINT((0.,0.));
#4 = IFCCARTESIANPOINT((5000.,0.));
#5 = IFCPOLYLINE((#1,#2));
#6 = IFCPOLYLINE((#3,#4));
#7 = IFCGRIDAXIS('X1',#5,.T.);
#8 = IFCGRIDAXIS('Y1',#6,.T.);
"""


class TestParseIfcContent:
    def test_parses_cartesian_points(self):
        points, _, _ = parse_ifc_content(SAMPLE_IFC)
        assert points[1] == (0.0, 1000.0)
        assert points[2] == (5000.0, 1000.0)
        assert points[3] == (0.0, 0.0)
        assert points[4] == (5000.0, 0.0)

    def test_parses_polylines(self):
        _, polylines, _ = parse_ifc_content(SAMPLE_IFC)
        assert polylines[5] == [1, 2]
        assert polylines[6] == [3, 4]

    def test_parses_grid_axes(self):
        _, _, grid_axes = parse_ifc_content(SAMPLE_IFC)
        assert grid_axes[7] == {'name': 'X1', 'poly_id': 5}
        assert grid_axes[8] == {'name': 'Y1', 'poly_id': 6}

    def test_empty_content(self):
        points, polylines, grid_axes = parse_ifc_content("")
        assert points == {}
        assert polylines == {}
        assert grid_axes == {}

    def test_ignores_z_coordinate(self):
        content = "#10 = IFCCARTESIANPOINT((100.,200.,300.));"
        points, _, _ = parse_ifc_content(content)
        assert points[10] == (100.0, 200.0)

    def test_handles_multiline_statements(self):
        # 改行をまたぐステートメントでも正しく解析できること
        content = "#1 = IFCCARTESIANPOINT\n((10.,20.));"
        points, _, _ = parse_ifc_content(content)
        assert points[1] == (10.0, 20.0)

    def test_ignores_invalid_coordinates(self):
        content = "#1 = IFCCARTESIANPOINT((abc,def));"
        points, _, _ = parse_ifc_content(content)
        assert 1 not in points

    def test_parses_multiple_points_in_polyline(self):
        content = "#1 = IFCPOLYLINE((#10,#20,#30));"
        _, polylines, _ = parse_ifc_content(content)
        assert polylines[1] == [10, 20, 30]


class TestResolveLines:
    def _build_data(self):
        points = {1: (0.0, 0.0), 2: (1000.0, 0.0), 3: (500.0, 0.0), 4: (500.0, 1000.0)}
        polylines = {10: [1, 2], 20: [3, 4]}
        grid_axes = {
            100: {'name': 'Y1', 'poly_id': 10},
            200: {'name': 'X1', 'poly_id': 20},
        }
        return points, polylines, grid_axes

    def test_resolves_line_coordinates(self):
        points, polylines, grid_axes = self._build_data()
        lines, _, _ = resolve_lines(points, polylines, grid_axes)
        coords = [(x1, y1, x2, y2) for x1, y1, x2, y2, _ in lines]
        assert (0.0, 0.0, 1000.0, 0.0) in coords
        assert (500.0, 0.0, 500.0, 1000.0) in coords

    def test_preserves_axis_name(self):
        points, polylines, grid_axes = self._build_data()
        lines, _, _ = resolve_lines(points, polylines, grid_axes)
        names = {name for *_, name in lines}
        assert 'X1' in names
        assert 'Y1' in names

    def test_deduplicates_identical_lines(self):
        points = {1: (0.0, 0.0), 2: (1000.0, 0.0)}
        polylines = {10: [1, 2], 20: [1, 2]}
        grid_axes = {
            100: {'name': 'A', 'poly_id': 10},
            200: {'name': 'B', 'poly_id': 20},
        }
        lines, _, _ = resolve_lines(points, polylines, grid_axes)
        assert len(lines) == 1

    def test_calculates_center(self):
        points = {1: (0.0, 0.0), 2: (2000.0, 0.0), 3: (1000.0, -1000.0), 4: (1000.0, 1000.0)}
        polylines = {10: [1, 2], 20: [3, 4]}
        grid_axes = {
            100: {'name': 'Y1', 'poly_id': 10},
            200: {'name': 'X1', 'poly_id': 20},
        }
        _, center_x, center_y = resolve_lines(points, polylines, grid_axes)
        assert center_x == pytest.approx(1000.0)
        assert center_y == pytest.approx(0.0)

    def test_returns_zero_center_when_no_lines(self):
        lines, center_x, center_y = resolve_lines({}, {}, {})
        assert lines == []
        assert center_x == 0.0
        assert center_y == 0.0

    def test_skips_missing_polyline_reference(self):
        points = {1: (0.0, 0.0), 2: (1000.0, 0.0)}
        polylines = {}
        grid_axes = {100: {'name': 'X1', 'poly_id': 99}}
        lines, _, _ = resolve_lines(points, polylines, grid_axes)
        assert lines == []

    def test_skips_missing_point_reference(self):
        points = {1: (0.0, 0.0)}
        polylines = {10: [1, 99]}
        grid_axes = {100: {'name': 'X1', 'poly_id': 10}}
        lines, _, _ = resolve_lines(points, polylines, grid_axes)
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


class TestRun:
    """vs モジュールをモックして run() の動作を検証する。"""

    def _make_vs_mock(self):
        vs_mock = MagicMock()
        vs_mock.Handle.return_value = object()
        vs_mock.GetObject.return_value = None
        vs_mock.LNewObj.return_value = None
        vs_mock.CreateCustomObjectPath.return_value = None
        return vs_mock

    def test_run_cancel(self):
        vs_mock = self._make_vs_mock()
        vs_mock.GetFileN.return_value = (False, '')

        with patch.dict('sys.modules', {'vs': vs_mock}):
            import importlib
            import vw_import_ifc_homeskz.grid as grid_module
            importlib.reload(grid_module)
            grid_module.run()

        vs_mock.AlrtDialog.assert_called_once_with("キャンセルされました。")

    def test_run_imports_lines(self):
        vs_mock = self._make_vs_mock()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False, encoding='utf-8') as f:
            f.write(SAMPLE_IFC)
            ifc_path = f.name

        try:
            vs_mock.GetFileN.return_value = (True, ifc_path)

            with patch.dict('sys.modules', {'vs': vs_mock}):
                import importlib
                import vw_import_ifc_homeskz.grid as grid_module
                importlib.reload(grid_module)
                grid_module.run()

            # 2 本の通り芯が描画されること
            completion_call = vs_mock.AlrtDialog.call_args[0][0]
            assert '2 本' in completion_call
        finally:
            os.unlink(ifc_path)

    def test_run_error_handling(self):
        vs_mock = self._make_vs_mock()
        vs_mock.GetFileN.return_value = (True, '/nonexistent/path/file.ifc')

        with patch.dict('sys.modules', {'vs': vs_mock}):
            import importlib
            import vw_import_ifc_homeskz.grid as grid_module
            importlib.reload(grid_module)
            grid_module.run()

        call_arg = vs_mock.AlrtDialog.call_args[0][0]
        assert 'エラーが発生しました' in call_arg
