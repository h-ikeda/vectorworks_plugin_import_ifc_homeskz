"""roof 命令の描画。野地板を屋根ツール (BeginRoof) で配置する。

野地板は VectorWorks の**屋根ツール**で描く。屋根版(屋根面)1 面ごとに単勾配の
屋根オブジェクトを ``vs.BeginRoof`` で作る。

**呼び出し列は VW 上で屋根を作成したドキュメントの VectorScript エクスポートに
一致させる**(ユーザー提供のエクスポートで確認した正規手順。#113):

1. ``vs.GetZVals()`` で作図レイヤの Z/ΔZ を退避し、``vs.SetZVals(軒高, 厚み)`` で
   屋根作成用の Z 基準(軒の絶対 Z)と厚み(ΔZ=野地板厚)を予約する。**屋根の
   厚みはこの ΔZ が担う**(エクスポートは ``SetRoofAttributes`` を使わない)。
2. ``vs.BeginRoof(p1, p2, upslope, rise, run, miter, vertPart)`` で軒(屋根軸)・
   upslope 定義点・勾配を与える。勾配はエクスポートの規約に合わせ
   **run=25.4(1 インチ)あたりの rise** に正規化する(例: 10 度 → rise≈4.479)。
   ``vertPart`` はエクスポートが厚み×sinθ を渡しているため同じ値を計算して渡す。
3. **``vs.EndGroup()`` の前、``BeginRoof`` 直後に** ``vs.Move3D(0, 0, 軒高)`` で
   作成中の屋根を軒の絶対 Z へ移動する(エクスポートと同じ順序)。
4. 2D 図形(屋根の水平投影外形の閉じたポリゴン)をテンプレートとして描き、
   ``vs.EndGroup()`` で確定する。
5. ``vs.SetZVals`` を退避した値へ復元する(エクスポートも作成後に復元する。
   以降のフェーズのオブジェクト作成へ影響を残さない)。
6. **高さの自己補正**: 確定した屋根の実際の軸 Z を ``vs.GetRoofFaceCoords`` で
   実測し、目標(軒の絶対 Z)との差分だけ ``vs.Move3D`` で移動する(床ツールと
   同じ確定後 Move3D の規約)。ストーリレベルにバインドされたレイヤでは
   ``SetZVals`` の Z がバインドに上書きされて効かず、屋根の軸がレイヤの高さ
   (軒高=地廻り)に落ちる(母屋下がりの屋根面が地廻り高さに張り付く不具合)
   ため、指定値を信じずに実測との差分で補正する。

**確定後の屋根オブジェクトへの後付け操作は、取得系(``GetRoofFaceCoords``/
``GetRoofFaceAttrib``)・高さ自己補正の差分 ``Move3D``(床ツールで実績のある
確定後 Move3D と同じ規約)・``SetClass`` に限る**。以前は確定後に
``SetRoofAttributes``(本来 ``CreateRoof`` が返す屋根コンテナ用の関数)で厚みを
設定していたが、``BeginRoof`` が作る屋根への呼び出しはエクスポートに現れず、
未定義動作で VectorWorks 本体がクラッシュする原因と考えられるため呼ばない(#113)。

**屋根が作れたかの判定は ``LNewObj`` の前後比較 + タイプ判別で行う**:
テンプレートとして描いた外形ポリゴン自体が最後に作成したオブジェクトになるため、
``LNewObj`` の NIL 判定だけでは ``BeginRoof`` の失敗を検出できない。屋根と確認
できたオブジェクトにだけ ``SetClass`` を行い、失敗時は外形ポリゴンの
フォールバックにとどめる(#113)。

クラッシュ診断のため各 vs 呼び出しの前後にトレース(``tracing.py``)を記録する。
"""
from __future__ import annotations

import math

import vs

from ..document import RoofCommand
from ..tracing import trace

# BeginRoof の固定パラメータ。VW のエクスポートに一致させる。
# miter(軒先の切り口): 1=垂直。
_ROOF_MITER = 1
# GetTypeN が返す 2D ポリゴンのタイプ番号。BeginRoof が屋根を作れなかった場合は
# テンプレートとして描いた外形ポリゴンが最後に作成したオブジェクトとして残るため、
# これを屋根と誤認して屋根専用の設定を呼ばないよう判別する。
_POLYGON_TYPE = 5
# BeginRoof へ渡す勾配の run 基準値 (mm)。VW のエクスポートは run=25.4(1 インチ)
# あたりの rise で勾配を表す(例: 10 度 → rise=4.479, run=25.4)。命令の rise/run は
# 屋根面の単位法線成分(rise=水平成分 dh・run=鉛直成分 nz)で比(=勾配)は同じため、
# 比を保ったまま run がこの基準値になるよう正規化して渡す。
_SLOPE_RUN_UNIT = 25.4
# 高さの自己補正で「補正不要」とみなす軸 Z の差 (mm)。
_Z_TOL = 0.5


def _roof_face_axis_z(coords: object) -> float | None:
    """``GetRoofFaceCoords`` の戻り値から屋根面の軸 Z(``Zaxis``)を取り出す。

    公式スタブの Python シグネチャは ``(axis1, axis2, Zaxis, upslope)``(4 要素、
    点はタプル)だが、環境によっては座標が平坦に展開された 7 要素
    ``(a1x, a1y, a2x, a2y, Zaxis, upX, upY)`` で返る可能性があるため両方を解釈する。
    解釈できない場合は None(補正しない)。
    """
    if not isinstance(coords, tuple):
        return None
    if len(coords) == 4 and isinstance(coords[2], (int, float)):
        return float(coords[2])
    if len(coords) == 7 and isinstance(coords[4], (int, float)):
        return float(coords[4])
    return None


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

    VW のエクスポートに一致する呼び出し列(モジュール docstring 参照)で屋根を作り、
    屋根と確認できたオブジェクトに ``SetClass`` を行う。厚みは ``SetZVals`` の
    ΔZ・高さは ``BeginRoof`` 直後の ``Move3D`` が担い、確定後の屋根へは
    ``SetRoofAttributes`` 等の後付け操作を行わない(#113 のクラッシュ対策)。
    屋根が作れなかった場合は外形ポリゴンにフォールバックする(テンプレートの
    ポリゴンが残っていればそれを使う)。
    """
    boundary = command['boundary']
    axis_start = command['axis_start']
    axis_end = command['axis_end']
    upslope = command['upslope']
    thickness = command['thickness']
    elevation = command['elevation']

    run = command['run']
    if run <= 0.0:
        # 勾配が定まらない(鉛直面等の退化した)命令は屋根を作らずフォールバック。
        trace('draw_roof: run<=0, fallback polygon')
        _draw_footprint(boundary)
        poly_h = vs.LNewObj()
        if poly_h != vs.Handle(0):
            vs.SetClass(poly_h, command['class'])
        return
    # 比を保ったまま run=25.4(1 インチ)基準へ正規化する(エクスポートの規約)。
    rise = command['rise'] * _SLOPE_RUN_UNIT / run
    # vertPart: エクスポートは 厚み×sinθ を渡す(sinθ = 単位法線の水平成分)。
    slope_len = math.hypot(command['rise'], run)
    vert_part = thickness * command['rise'] / slope_len

    # 作図レイヤの Z/ΔZ を退避し、屋根作成用の Z 基準(軒高)と厚みを予約する。
    z_vals = vs.GetZVals()
    if isinstance(z_vals, tuple) and len(z_vals) == 2:
        saved_z, saved_dz = z_vals
    else:
        saved_z, saved_dz = 0.0, 0.0
    trace(f'draw_roof: SetZVals z={elevation:.1f} dz={thickness:.1f} '
          f'(saved z={saved_z:.1f} dz={saved_dz:.1f})')
    vs.SetZVals(elevation, thickness)

    # BeginRoof の成否を判定するため、直前の最終作成オブジェクトを記録する。
    before = vs.LNewObj()

    trace(
        f'draw_roof: BeginRoof p1=({axis_start[0]:.1f},{axis_start[1]:.1f}) '
        f'p2=({axis_end[0]:.1f},{axis_end[1]:.1f}) '
        f'up=({upslope[0]:.1f},{upslope[1]:.1f}) '
        f'rise={rise:.4f} run={_SLOPE_RUN_UNIT} vert={vert_part:.4f}')
    vs.BeginRoof(
        (axis_start[0], axis_start[1]),
        (axis_end[0], axis_end[1]),
        (upslope[0], upslope[1]),
        rise,
        _SLOPE_RUN_UNIT,
        _ROOF_MITER,
        vert_part,
    )
    # 軒(屋根軸)を天端の絶対 Z へ。エクスポートと同じく BeginRoof 直後
    # (EndGroup の前)に移動する(BeginRoof は軸を Z=0 で作るため)。
    trace(f'draw_roof: Move3D z={elevation:.1f}')
    vs.Move3D(0.0, 0.0, elevation)
    trace('draw_roof: drawing footprint')
    _draw_footprint(boundary)
    trace('draw_roof: footprint drawn, EndGroup')
    vs.EndGroup()
    trace('draw_roof: EndGroup returned')
    # 作図レイヤの Z/ΔZ を復元する(以降のオブジェクト作成へ影響を残さない)。
    vs.SetZVals(saved_z, saved_dz)
    roof = vs.LNewObj()

    if roof == vs.Handle(0) or roof == before:
        # 何も作られなかった: フォールバックの外形ポリゴンを描く。
        trace('draw_roof: nothing created, fallback polygon')
        _draw_footprint(boundary)
        poly_h = vs.LNewObj()
        if poly_h != vs.Handle(0) and poly_h != before:
            vs.SetClass(poly_h, command['class'])
        return

    obj_type = vs.GetTypeN(roof)
    trace(f'draw_roof: created object type={obj_type}')
    if obj_type == _POLYGON_TYPE:
        # BeginRoof が屋根を作れず、テンプレートの外形ポリゴンだけが残った:
        # そのポリゴンをフォールバック外形として扱う。屋根専用の設定は呼ばない。
        vs.SetClass(roof, command['class'])
        return

    # 高さの自己補正: ストーリレベルにバインドされたレイヤでは SetZVals の Z が
    # バインドに上書きされ、屋根の軸がレイヤの高さ(軒高=地廻り)に落ちる。
    # 指定値を信じず、確定した屋根の実際の軸 Z(GetRoofFaceCoords の Zaxis)を
    # 実測して目標(軒の絶対 Z)との差分だけ Move3D で移動する(確定直後の屋根が
    # 最後に作成したオブジェクトのため、床ツールの確定後 Move3D と同じ規約)。
    coords = vs.GetRoofFaceCoords(roof)
    attrib = vs.GetRoofFaceAttrib(roof)
    trace(f'draw_roof: coords={coords} attrib={attrib}')
    z_actual = _roof_face_axis_z(coords)
    if z_actual is not None and abs(elevation - z_actual) > _Z_TOL:
        delta = elevation - z_actual
        trace(f'draw_roof: correcting axis z {z_actual:.1f} -> {elevation:.1f} '
              f'(Move3D dz={delta:.1f})')
        vs.Move3D(0.0, 0.0, delta)

    trace('draw_roof: SetClass')
    vs.SetClass(roof, command['class'])
    trace('draw_roof: done')


def execute_roofs(commands: list[RoofCommand]) -> int:
    """roof 命令のリストを描画し、配置数を返す。

    配置先レイヤ(``n-野地板``)が存在しない命令はスキップする(レイヤは story 命令が
    生成する。未生成 = その階のストーリ設定がスキップされた場合であり、勝手に
    レイヤを作らない。垂木・火打等と同じ扱い)。
    """
    count = 0
    for i, command in enumerate(commands):
        layer = command['layer']
        if vs.GetObject(layer) == vs.Handle(0):
            trace(f'execute_roofs: [{i}] skip (layer {layer} missing)')
            continue
        trace(f'execute_roofs: [{i}] layer={layer}')
        vs.Layer(layer)
        draw_roof(command)
        count += 1
    return count
