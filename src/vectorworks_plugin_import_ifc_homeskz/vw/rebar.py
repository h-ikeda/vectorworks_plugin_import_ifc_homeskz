"""rebar 命令の描画。基礎の配筋 PIO「鉄筋」を 3D パス図形として配置する。

各命令について、配置先レイヤ(``F-立上り`` / ``F-底盤``)をアクティブにしてから、
命令の 3D パス(梁モード=梁天端の中心線・スラブモード=底盤天端の外形)を
``vs.Poly3D`` で作り、``vs.CreateCustomObjectPath`` でカスタム PIO「鉄筋」を配置する。
PIO 本体のクラスを ``vs.SetClass`` で命令の ``class`` に設定し、描画属性をすべて
クラス属性に従わせてから、モード・配筋仕様を PIO のパラメータ(レコードフィールド)に
``vs.SetRField`` で設定して ``vs.ResetObject`` でリセットする。

**リセット時に PIO 本体(=姉妹プロジェクト vectorworks-plugin-rebar のコード)が
パス・パラメータから平面線・3D 鉄筋・断面 2D コンポーネントを描く**(本リポジトリは
PIO の配置とパラメータ設定までを担い、配筋の描画ロジックは持たない)。

PIO 名「鉄筋」・パラメータ名(``Mode`` / ``MainBar`` / ``DistBar`` / ``SlabThickness`` /
``SectionSize`` / ``TopBars`` / ``BottomBars`` / ``Stirrup``)は VectorWorks 側の
プラグイン登録名(および vectorworks-plugin-rebar の ``vw/pio.py`` の ``PARAM_*``)と
一致させる必要がある。配置先レイヤが存在しない命令、PIO が作れない(プラグイン未登録で
``CreateCustomObjectPath`` が NIL)命令はスキップする。
"""
from __future__ import annotations

from typing import Any

import vs

from ..document import RebarCommand

# 配筋プラグインオブジェクトの内部プラグイン名・レコード名(VectorWorks 側で
# この名前の 3D パス図形プラグインを登録すること)。
_PLUGIN_NAME = '鉄筋'
# PIO のパラメータ(レコードフィールド)名。vectorworks-plugin-rebar の
# vw/pio.py の PARAM_* と一致させる。
_PARAM_MODE = 'Mode'
_PARAM_MAIN_BAR = 'MainBar'
_PARAM_DIST_BAR = 'DistBar'
_PARAM_SLAB_THICKNESS = 'SlabThickness'
_PARAM_SECTION_SIZE = 'SectionSize'
_PARAM_TOP_BARS = 'TopBars'
_PARAM_BOTTOM_BARS = 'BottomBars'
_PARAM_STIRRUP = 'Stirrup'
# Mode ポップアップの表示値(PIO 側は表示値に "梁" を含めば梁モード、それ以外は
# スラブモードと判定する)。
_MODE_LABEL_SLAB = 'スラブ'
_MODE_LABEL_BEAM = '梁'


def _set_all_attributes_by_class(obj: Any) -> None:
    """オブジェクトの描画属性(太さ・色・パターン・透明度等)をすべてクラス属性に従わせる。

    ``SetClass`` はクラスを割り当てるだけで各描画属性は by-instance の既定値のまま残る
    ため、属性ごとの by-class 設定関数を個別に呼ぶ(``vw/column_mark.py`` と同じ規約)。
    リセットで再描画される鉄筋は PIO の属性を継承するため、``ResetObject`` より前に
    設定する。
    """
    vs.SetPenColorByClass(obj)
    vs.SetFillColorByClass(obj)
    vs.SetLWByClass(obj)
    vs.SetLSByClass(obj)
    vs.SetFPatByClass(obj)
    vs.SetMarkerByClass(obj)
    vs.SetOpacityByClass(obj)


def _create_path(command: RebarCommand) -> Any:
    """rebar 命令の 3D パス頂点から 3D ポリゴンを作り、そのハンドルを返す。

    スラブモード(``closed=True``)は閉じた多角形、梁モード(``closed=False``)は
    開いた線として作る。作成モード(開/閉)を明示設定してから ``vs.Poly3D`` で
    全頂点を一度に与える(``vw`` の配筋 PIO 側 ``draw.py`` と同じ 3D ポリゴンの作り方)。
    """
    if command['closed']:
        vs.ClosePoly()
    else:
        vs.OpenPoly()
    coords: list[float] = []
    for x, y, z in command['path']:
        coords.extend((x, y, z))
    vs.Poly3D(*coords)
    return vs.LNewObj()


def _set_rebar_params(obj: Any, command: RebarCommand) -> None:
    """rebar 命令のモード・配筋仕様を PIO のパラメータに設定する。

    梁モードは SectionSize/TopBars/BottomBars/Stirrup、スラブモードは
    MainBar/DistBar/SlabThickness を設定する。Mode ポップアップは表示値
    (``梁`` / ``スラブ``)を渡す。
    """
    if command['mode'] == 'beam':
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_MODE, _MODE_LABEL_BEAM)
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_SECTION_SIZE, command['section_size'])
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_TOP_BARS, command['top_bars'])
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_BOTTOM_BARS, command['bottom_bars'])
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_STIRRUP, command['stirrup'])
    else:
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_MODE, _MODE_LABEL_SLAB)
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_MAIN_BAR, command['main_bar'])
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_DIST_BAR, command['dist_bar'])
        vs.SetRField(obj, _PLUGIN_NAME, _PARAM_SLAB_THICKNESS,
                     f"{command['slab_thickness']:g}")


def draw_rebar(command: RebarCommand) -> bool:
    """rebar 命令 1 件を鉄筋 PIO として配置する。

    3D パスを作って ``vs.CreateCustomObjectPath`` で PIO を挿入し、PIO 本体のクラス・
    描画属性を設定してから配筋仕様のパラメータを設定し ``vs.ResetObject`` でリセットする。
    PIO が作れない(プラグイン未登録等で NIL)場合は False。
    """
    path_handle = _create_path(command)
    obj = vs.CreateCustomObjectPath(_PLUGIN_NAME, path_handle, vs.Handle(0))
    if obj == vs.Handle(0):
        return False
    vs.SetClass(obj, command['class'])
    _set_all_attributes_by_class(obj)
    _set_rebar_params(obj, command)
    vs.ResetObject(obj)
    return True


def execute_rebars(commands: list[RebarCommand]) -> int:
    """rebar 命令のリストを描画し、配置数を返す。

    配置先レイヤ(``F-立上り`` / ``F-底盤``)が存在しない命令はスキップする(レイヤは
    story 命令が生成する)。PIO が作れない命令も配置数に数えない。
    """
    count = 0
    for command in commands:
        layer = command['layer']
        if vs.GetObject(layer) == vs.Handle(0):
            continue
        vs.Layer(layer)
        if draw_rebar(command):
            count += 1
    return count
