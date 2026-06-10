"""描画フェーズ (vw.member) のテスト。vs をモックし手書きの member 命令で検証する。"""
import importlib
from unittest.mock import MagicMock, patch

import pytest


def make_member_command(layer='1-横架材天端', member_id='120×180 - 杉',
                        start=(0.0, 0.0), end=(3000.0, 0.0),
                        width=120.0, height=180.0, elevation=473.0):
    return {
        'layer': layer,
        'member_id': member_id,
        'start': list(start),
        'end': list(end),
        'width': width,
        'height': height,
        'elevation': elevation,
    }


def _make_vs_mock(existing_layers=()):
    """execute_members() 用 vs モック。

    existing_layers に含まれるレイヤ名は GetObject で非 null を返す。
    CreateCustomObjectPath は非 null を返し (プラグイン利用可能) 、
    SetRField / ResetObject の呼び出しを追跡できる。
    """
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


def _run_execute_members(vs_mock, commands):
    with patch.dict('sys.modules', {'vs': vs_mock}):
        import vectorworks_plugin_import_ifc_homeskz.vw.member as vw_member
        importlib.reload(vw_member)
        return vw_member.execute_members(commands)


class TestExecuteMembers:
    def test_empty_commands_return_zero(self):
        vs_mock = _make_vs_mock()
        count = _run_execute_members(vs_mock, [])
        assert count == 0
        vs_mock.Layer.assert_not_called()

    def test_returns_count_of_drawn_members(self):
        vs_mock = _make_vs_mock(existing_layers={'1-横架材天端'})
        count = _run_execute_members(vs_mock, [
            make_member_command(start=(0.0, 0.0)),
            make_member_command(start=(0.0, 1000.0)),
        ])
        assert count == 2

    def test_skips_command_when_layer_missing(self):
        """配置先レイヤが未生成の命令はスキップする（勝手にレイヤを作らない）。"""
        vs_mock = _make_vs_mock(existing_layers=set())
        count = _run_execute_members(vs_mock, [make_member_command()])
        assert count == 0
        vs_mock.Layer.assert_not_called()
        vs_mock.CreateLayer.assert_not_called()

    def test_switches_to_command_layer(self):
        vs_mock = _make_vs_mock(existing_layers={'1-横架材天端', '2-横架材天端'})
        _run_execute_members(vs_mock, [
            make_member_command(layer='1-横架材天端'),
            make_member_command(layer='2-横架材天端'),
        ])
        layer_calls = [c.args[0] for c in vs_mock.Layer.call_args_list]
        assert '1-横架材天端' in layer_calls
        assert '2-横架材天端' in layer_calls

    def test_draws_path_locally_and_moves_to_position(self):
        """パスはローカル原点から方向ベクトルで作り、Move3D で絶対位置へ移動する。"""
        vs_mock = _make_vs_mock(existing_layers={'1-横架材天端'})
        nurbs_calls = []
        vertex_calls = []
        move3d_calls = []

        def capture_nurbs(x, y, z, closed, order):
            nurbs_calls.append((x, y))
            return object()

        def capture_vertex(h, x, y, z):
            vertex_calls.append((x, y))

        def capture_move3d(x, y, z):
            move3d_calls.append((x, y, z))

        vs_mock.CreateNurbsCurve.side_effect = capture_nurbs
        vs_mock.AddVertex3D.side_effect = capture_vertex
        vs_mock.Move3D.side_effect = capture_move3d

        _run_execute_members(vs_mock, [
            make_member_command(start=(500.0, 500.0), end=(1100.0, 500.0), elevation=473.0),
        ])

        # パスはローカル原点 (0, 0) から方向ベクトル (600, 0) へ
        assert nurbs_calls == [(0, 0)]
        assert vertex_calls == [(pytest.approx(600.0), pytest.approx(0.0))]
        # Move3D で始端 (500, 500, 473) へ移動
        assert any(
            abs(x - 500.0) < 1e-6 and abs(y - 500.0) < 1e-6 and abs(z - 473.0) < 1e-6
            for x, y, z in move3d_calls
        )

    def test_sets_member_id_record_field(self):
        vs_mock = _make_vs_mock(existing_layers={'1-横架材天端'})
        _run_execute_members(vs_mock, [
            make_member_command(member_id='120×180 - 杉対称異等級集成材E105-F355'),
        ])
        set_rfield_args = [c.args for c in vs_mock.SetRField.call_args_list]
        member_id_values = [v for _, _, _, v in set_rfield_args]
        assert '120×180 - 杉対称異等級集成材E105-F355' in member_id_values

    def test_fallback_to_line_when_plugin_unavailable(self):
        """構造材プラグインが利用できない場合に通常線にフォールバックする。"""
        vs_mock = _make_vs_mock(existing_layers={'1-横架材天端'})
        # プラグインが存在しない → Handle(0) を返す
        vs_mock.CreateCustomObjectPath.return_value = vs_mock.Handle.return_value

        count = _run_execute_members(vs_mock, [make_member_command()])

        # フォールバックでも 1 本描画される
        assert count == 1
        # SetRField は呼ばれない (フォールバック時)
        vs_mock.SetRField.assert_not_called()
