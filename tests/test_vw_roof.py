"""描画フェーズ (vw.roof) のテスト。vs をモックし手書きの命令で検証する。"""
from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock, patch

from vectorworks_plugin_import_ifc_homeskz.document import RoofCommand

# GetTypeN のタイプ番号: 2D ポリゴン(テンプレート/フォールバック外形)。
_POLYGON_TYPE = 5
# 屋根オブジェクトのタイプ番号(ポリゴン以外なら何でもよい。実値は VW 依存)。
_ROOF_TYPE = 89


def make_command() -> RoofCommand:
    # 軒(y=0, z=6000)から棟(y=3000)へ立ち上がる 4m×3m の片流れ屋根面。
    return {
        'layer': 'R-野地板',
        'class': '04構造-02木造-06耐力面材-03屋根',
        'boundary': [[0.0, 0.0], [4000.0, 0.0], [4000.0, 3000.0], [0.0, 3000.0]],
        'axis_start': [0.0, 0.0],
        'axis_end': [4000.0, 0.0],
        'upslope': [0.0, 3000.0],
        'rise': 1000.0,
        'run': 3000.0,
        'thickness': 12.0,
        'elevation': 6000.0,
    }


def _make_vs_mock(
    existing_layers: set[str],
    created: object | None = None,
    created_type: int = _ROOF_TYPE,
) -> MagicMock:
    """vs モックを作る。

    ``created`` は BeginRoof + テンプレート + EndGroup の後に LNewObj が返す
    オブジェクト(None なら「何も作られない」= LNewObj は常に NIL)。
    ``created_type`` はそのオブジェクトの GetTypeN が返すタイプ番号
    (屋根=ポリゴン以外、テンプレートのポリゴンが残った失敗時=5)。
    draw_roof は BeginRoof の前に LNewObj で直前のオブジェクトを記録し前後比較で
    成否を判定するため、LNewObj は 1 回目(前)= NIL、2 回目以降(後)= created を返す。
    """
    vs_mock = MagicMock()
    null_handle = object()
    vs_mock.Handle.return_value = null_handle

    def get_obj(name: str) -> object:
        return ('HANDLE_' + name) if name in existing_layers else null_handle

    vs_mock.GetObject.side_effect = get_obj

    calls = {'n': 0}

    def lnewobj() -> object:
        calls['n'] += 1
        if calls['n'] == 1 or created is None:
            return null_handle
        return created

    vs_mock.LNewObj.side_effect = lnewobj
    vs_mock.GetTypeN.return_value = created_type
    return vs_mock


def _load(vs_mock: MagicMock) -> Any:
    with patch.dict('sys.modules', {'vs': vs_mock}):
        import vectorworks_plugin_import_ifc_homeskz.vw.roof as vw_roof
        importlib.reload(vw_roof)
        return vw_roof


class TestExecuteRoofs:
    def test_creates_roof_with_begin_roof(self) -> None:
        vs_mock = _make_vs_mock({'R-野地板'}, created=object())
        vw_roof = _load(vs_mock)

        count = vw_roof.execute_roofs([make_command()])

        assert count == 1
        vs_mock.Layer.assert_called_once_with('R-野地板')
        # 屋根ツール(BeginRoof)で作図し EndGroup で確定する。
        vs_mock.BeginRoof.assert_called_once()
        args = vs_mock.BeginRoof.call_args.args
        assert args[0] == (0.0, 0.0)       # axis_start (p1)
        assert args[1] == (4000.0, 0.0)    # axis_end (p2)
        assert args[2] == (0.0, 3000.0)    # upslope
        assert args[3] == 1000.0           # rise
        assert args[4] == 3000.0           # run
        vs_mock.EndGroup.assert_called_once()

    def test_sets_thickness_via_roof_attributes(self) -> None:
        roof_handle = object()
        vs_mock = _make_vs_mock({'R-野地板'}, created=roof_handle)
        vw_roof = _load(vs_mock)
        vw_roof.execute_roofs([make_command()])
        # 厚みは SetRoofAttributes の 4 番目(roofThickDistance)引数に 12mm。
        vs_mock.SetRoofAttributes.assert_called_once()
        assert vs_mock.SetRoofAttributes.call_args.args[0] is roof_handle
        assert vs_mock.SetRoofAttributes.call_args.args[3] == 12.0

    def test_moves_to_eaves_elevation(self) -> None:
        roof_handle = object()
        vs_mock = _make_vs_mock({'R-野地板'}, created=roof_handle)
        vw_roof = _load(vs_mock)
        vw_roof.execute_roofs([make_command()])
        # BeginRoof は軸を Z=0 で作るため、軒の絶対 Z へ移動する。対象を明示する
        # ためハンドル指定の Move3DObj を使う(Move3D は最後に作成した 3D
        # オブジェクトが対象で、意図しないオブジェクトを動かすおそれがある)。
        vs_mock.Move3DObj.assert_called_once_with(roof_handle, 0.0, 0.0, 6000.0)
        vs_mock.Move3D.assert_not_called()

    def test_sets_class(self) -> None:
        vs_mock = _make_vs_mock({'R-野地板'}, created=object())
        vw_roof = _load(vs_mock)
        vw_roof.execute_roofs([make_command()])
        vs_mock.SetClass.assert_called_once()
        assert vs_mock.SetClass.call_args.args[1] == '04構造-02木造-06耐力面材-03屋根'

    def test_does_not_reset_roof_object(self) -> None:
        # 屋根(非パラメトリックオブジェクト)への ResetObject は呼ばない
        # (未定義動作でクラッシュの一因になりうるため。#113)。
        vs_mock = _make_vs_mock({'R-野地板'}, created=object())
        vw_roof = _load(vs_mock)
        vw_roof.execute_roofs([make_command()])
        vs_mock.ResetObject.assert_not_called()

    def test_skips_when_layer_missing(self) -> None:
        vs_mock = _make_vs_mock(set(), created=object())
        vw_roof = _load(vs_mock)

        count = vw_roof.execute_roofs([make_command()])

        assert count == 0
        vs_mock.BeginRoof.assert_not_called()

    def test_falls_back_to_polygon_when_roof_unavailable(self) -> None:
        # LNewObj が NIL のまま = 屋根もテンプレートも作られない環境。
        vs_mock = _make_vs_mock({'R-野地板'}, created=None)
        vw_roof = _load(vs_mock)

        count = vw_roof.execute_roofs([make_command()])

        # フォールバックでも配置数には数える。SetRoofAttributes は呼ばれない。
        assert count == 1
        vs_mock.SetRoofAttributes.assert_not_called()
        vs_mock.LineTo.assert_called()

    def test_leftover_template_polygon_is_not_treated_as_roof(self) -> None:
        # BeginRoof が屋根を作れずテンプレートの外形ポリゴンだけが残った場合、
        # LNewObj は NIL ではなくそのポリゴンを返す。ポリゴンを屋根と誤認して
        # SetRoofAttributes / Move3DObj を呼ぶと VW がクラッシュするため(#113)、
        # タイプ判別でフォールバック扱いにし、クラス設定だけを行う。
        poly_handle = object()
        vs_mock = _make_vs_mock(
            {'R-野地板'}, created=poly_handle, created_type=_POLYGON_TYPE)
        vw_roof = _load(vs_mock)

        count = vw_roof.execute_roofs([make_command()])

        assert count == 1
        vs_mock.SetRoofAttributes.assert_not_called()
        vs_mock.Move3DObj.assert_not_called()
        vs_mock.SetClass.assert_called_once()
        assert vs_mock.SetClass.call_args.args[0] is poly_handle
