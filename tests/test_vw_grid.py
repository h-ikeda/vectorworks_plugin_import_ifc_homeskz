"""描画フェーズ (vw.grid) のテスト。vs をモックし手書きの grid 命令で検証する。"""
import importlib
from unittest.mock import MagicMock, patch


def make_grid_command(label='X1', layer='共通', class_name='X通りクラス',
                      start=(0.0, -1000.0), end=(0.0, 1000.0)):
    return {
        'label': label,
        'layer': layer,
        'class': class_name,
        'start': list(start),
        'end': list(end),
    }


def _make_vs_mock(existing_layers=()):
    vs_mock = MagicMock()
    null_handle = object()
    non_null_handle = object()
    vs_mock.Handle.return_value = null_handle
    vs_mock.LNewObj.return_value = non_null_handle
    vs_mock.CreateCustomObjectPath.return_value = non_null_handle

    def get_obj(name):
        return non_null_handle if name in existing_layers else null_handle

    vs_mock.GetObject.side_effect = get_obj
    return vs_mock


def _run_execute_grids(vs_mock, commands):
    with patch.dict('sys.modules', {'vs': vs_mock}):
        import vectorworks_plugin_import_ifc_homeskz.vw.grid as vw_grid
        importlib.reload(vw_grid)
        return vw_grid.execute_grids(commands)


class TestExecuteGrids:
    def test_returns_drawn_count(self):
        vs_mock = _make_vs_mock()
        count = _run_execute_grids(vs_mock, [
            make_grid_command(label='X1'),
            make_grid_command(label='Y1', start=(-1000.0, 0.0), end=(1000.0, 0.0)),
        ])
        assert count == 2

    def test_empty_commands_return_zero(self):
        vs_mock = _make_vs_mock()
        count = _run_execute_grids(vs_mock, [])
        assert count == 0
        vs_mock.Layer.assert_not_called()

    def test_creates_missing_layer_and_activates(self):
        vs_mock = _make_vs_mock()
        _run_execute_grids(vs_mock, [make_grid_command(layer='共通')])
        vs_mock.CreateLayer.assert_called_once_with('共通', 1)
        vs_mock.Layer.assert_called_with('共通')

    def test_does_not_recreate_existing_layer(self):
        vs_mock = _make_vs_mock(existing_layers={'共通'})
        _run_execute_grids(vs_mock, [make_grid_command(layer='共通')])
        vs_mock.CreateLayer.assert_not_called()
        vs_mock.Layer.assert_called_with('共通')

    def test_creates_grid_axis_with_record_fields(self):
        vs_mock = _make_vs_mock()
        _run_execute_grids(vs_mock, [make_grid_command(label='X5')])

        vs_mock.CreateCustomObjectPath.assert_called_once()
        assert vs_mock.CreateCustomObjectPath.call_args.args[0] == 'GridAxis'

        rfield_calls = [c.args for c in vs_mock.SetRField.call_args_list]
        assert any(args[2] == 'Label' and args[3] == 'X5' for args in rfield_calls)
        assert any(args[2] == 'ShowBubbleAt' and args[3] == 'Start Point'
                   for args in rfield_calls)

    def test_sets_class_from_command(self):
        vs_mock = _make_vs_mock()
        _run_execute_grids(vs_mock, [make_grid_command(class_name='任意のクラス')])
        class_names = [c.args[1] for c in vs_mock.SetClass.call_args_list]
        assert '任意のクラス' in class_names

    def test_fallback_to_line_when_plugin_unavailable(self):
        vs_mock = _make_vs_mock()
        vs_mock.CreateCustomObjectPath.return_value = vs_mock.Handle.return_value

        count = _run_execute_grids(vs_mock, [make_grid_command()])

        # フォールバックでも 1 本として数える。SetRField は呼ばれない
        assert count == 1
        vs_mock.SetRField.assert_not_called()
        vs_mock.SetClass.assert_called()
