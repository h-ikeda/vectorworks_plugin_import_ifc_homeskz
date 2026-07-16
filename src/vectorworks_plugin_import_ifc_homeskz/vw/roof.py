"""roof 命令の描画。野地板を屋根ツール (BeginRoof) で配置する。

野地板は VectorWorks の**屋根ツール**で描く。屋根版(屋根面)1 面ごとに単勾配の
屋根オブジェクトを ``vs.BeginRoof`` で作る。``BeginRoof`` は軒(屋根軸)の 2 点
``axis_start``/``axis_end``・棟側を指す ``upslope`` 定義点・勾配 ``rise``/``run`` を
受け取り、続けて 2D 図形(屋根の水平投影外形の閉じたポリゴン)をテンプレートとして
描いてから ``vs.EndGroup()`` で確定する(床ツール ``BeginFloor``/``EndGroup`` と同じ
手続き型オブジェクト作成パターン)。作成後、厚みを ``vs.SetRoofAttributes`` で
野地板厚(12mm)に設定し、軒が命令の ``elevation``(絶対 Z)になるよう
``vs.Move3DObj`` で移動する(``BeginRoof`` は軸を Z=0 で作るため)。

**屋根が作れたかの判定は ``LNewObj`` の前後比較 + タイプ判別で行う**:
テンプレートとして描いた外形ポリゴン自体が最後に作成したオブジェクトになるため、
``LNewObj`` の NIL 判定だけでは ``BeginRoof`` の失敗を検出できない。失敗時に
残ったポリゴンや直前に作成した別オブジェクト(垂木 PIO 等)へ屋根専用の
``SetRoofAttributes``・``Move3D``・``ResetObject`` を呼ぶと未定義動作となり
VectorWorks 本体がクラッシュする(#113)。屋根と確認できたオブジェクトにだけ
屋根専用の設定を行い、失敗時は外形ポリゴンのフォールバックにとどめる。

屋根ツールの高さ・勾配・軒の与え方(``BeginRoof`` のパラメータ順・``EndGroup`` での
確定・``SetRoofAttributes`` の厚み・``Move3DObj`` の絶対 Z)は他の要素と同じく
VectorWorks 上で最終確認する方針(冒頭の名前付き定数に集約)。
"""
from __future__ import annotations

import vs

from ..document import RoofCommand

# BeginRoof / SetRoofAttributes の固定パラメータ。VW 上で最終確認する。
# miter(軒先の切り口): 1=垂直。vertPart は double miter 用の鉛直寸法(未使用=0)。
_ROOF_MITER = 1
_ROOF_VERT_PART = 0.0
# SetRoofAttributes: 妻壁生成なし・支持材の食い込み 0。
_ROOF_GEN_GABLE = False
_ROOF_BEARING_INSET = 0.0
# GetTypeN が返す 2D ポリゴンのタイプ番号。BeginRoof が屋根を作れなかった場合は
# テンプレートとして描いた外形ポリゴンが最後に作成したオブジェクトとして残るため、
# これを屋根と誤認して屋根専用の設定(SetRoofAttributes 等)を呼ばないよう判別する。
_POLYGON_TYPE = 5


def _draw_footprint(boundary: list[list[float]]) -> None:
    """屋根の水平投影外形を閉じたポリゴンとして描く(床ツールと同じ手続き)。"""
    vs.ClosePoly()
    vs.BeginPoly()
    vs.MoveTo(boundary[0][0], boundary[0][1])
    for point in boundary[1:]:
        vs.LineTo(point[0], point[1])
    vs.EndPoly()


def draw_roof(command: RoofCommand) -> None:
    """roof 命令 1 件を屋根ツール (BeginRoof) で描画する。

    ``vs.BeginRoof`` で軒(軸)・upslope・勾配を与え、屋根の水平投影外形を
    テンプレートとして描いて ``vs.EndGroup()`` で屋根オブジェクトを確定する。作成後、
    厚みを ``vs.SetRoofAttributes`` で野地板厚(命令の ``thickness``)に設定し、軒を
    命令の ``elevation``(絶対 Z)へ ``vs.Move3DObj`` で移動する(``BeginRoof`` は軸を
    Z=0 で作るため)。

    **屋根が生成できたかは ``LNewObj`` の前後比較とタイプ判別で確認する**。
    テンプレートの外形ポリゴン自体が ``LNewObj`` で返るため NIL 判定では失敗を
    検出できず、失敗時に残ったポリゴンや直前の別オブジェクトへ屋根専用の関数を
    呼ぶと VectorWorks がクラッシュする(#113)。屋根が作れなかった場合は外形
    ポリゴンにフォールバックする(テンプレートのポリゴンが残っていればそれを使う)。
    """
    boundary = command['boundary']
    axis_start = command['axis_start']
    axis_end = command['axis_end']
    upslope = command['upslope']

    # BeginRoof の成否を判定するため、直前の最終作成オブジェクトを記録する。
    before = vs.LNewObj()

    vs.BeginRoof(
        (axis_start[0], axis_start[1]),
        (axis_end[0], axis_end[1]),
        (upslope[0], upslope[1]),
        command['rise'],
        command['run'],
        _ROOF_MITER,
        _ROOF_VERT_PART,
    )
    _draw_footprint(boundary)
    vs.EndGroup()
    roof = vs.LNewObj()

    if roof == vs.Handle(0) or roof == before:
        # 何も作られなかった: フォールバックの外形ポリゴンを描く。
        _draw_footprint(boundary)
        poly_h = vs.LNewObj()
        if poly_h != vs.Handle(0) and poly_h != before:
            vs.SetClass(poly_h, command['class'])
        return

    if vs.GetTypeN(roof) == _POLYGON_TYPE:
        # BeginRoof が屋根を作れず、テンプレートの外形ポリゴンだけが残った:
        # そのポリゴンをフォールバック外形として扱う。屋根専用の設定
        # (SetRoofAttributes・Move3DObj)はポリゴンに対して未定義動作のため呼ばない。
        vs.SetClass(roof, command['class'])
        return

    # 厚みを野地板厚に設定(BeginRoof には厚み引数が無いため後付けで設定する)。
    vs.SetRoofAttributes(
        roof, _ROOF_GEN_GABLE, _ROOF_BEARING_INSET,
        command['thickness'], _ROOF_MITER, _ROOF_VERT_PART)
    # 軒(屋根軸)を天端の絶対 Z へ。BeginRoof は軸を Z=0 で作るため実際の高さへ
    # 移動する。対象を明示するためハンドル指定の Move3DObj を使う(Move3D は
    # 「最後に作成した 3D オブジェクト」が対象で、意図しないオブジェクトを
    # 動かすおそれがある)。
    vs.Move3DObj(roof, 0.0, 0.0, command['elevation'])
    vs.SetClass(roof, command['class'])


def execute_roofs(commands: list[RoofCommand]) -> int:
    """roof 命令のリストを描画し、配置数を返す。

    配置先レイヤ(``n-野地板``)が存在しない命令はスキップする(レイヤは story 命令が
    生成する。未生成 = その階のストーリ設定がスキップされた場合であり、勝手に
    レイヤを作らない。垂木・火打等と同じ扱い)。
    """
    count = 0
    for command in commands:
        layer = command['layer']
        if vs.GetObject(layer) == vs.Handle(0):
            continue
        vs.Layer(layer)
        draw_roof(command)
        count += 1
    return count
