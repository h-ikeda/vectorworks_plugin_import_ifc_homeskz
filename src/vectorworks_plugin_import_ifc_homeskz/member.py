"""横架材天端レイヤに土台・梁・桁を描画するモジュール。

IFC の IfcBeam / IfcMember を走査し、各階の横架材天端レイヤに
VectorWorks 構造材ツール (CreateCustomObjectPath('StructuralMember', ...)) で配置する。
構造材 ID は断面寸法と材種から "{幅}×{背} - {材種}" の形式で自動生成する。
"""
import math

import vs

from .grid import resolve_lines
from .story import LEVEL_BEAM_TOP, LEVEL_EAVES, layer_prefix_for, resolve_beam_top_offset

PLUGIN_NAME = 'StructuralMember'

LAYER_SUFFIX = LEVEL_BEAM_TOP
_IFC_MEMBER_TYPES = ('IfcBeam', 'IfcMember')

# 仕口スナップ: 負け端点と交差部材中心線との最大許容距離 (mm)
_JOIN_TOLERANCE = 10.0


def _get_placement_2d(element):
    """IfcProduct のローカル配置から 2D 座標 (ox, oy, dx, dy) を返す。

    取得できない場合は None を返す。
    dx, dy は梁軸方向の単位ベクトル（Axis の XY 成分）。
    ホームズ君 IFC では押し出し方向が常にローカル Z (Axis) なので
    梁の延伸方向 = Axis 属性を使う。Axis が未設定の場合は (1.0, 0.0) を使う。
    """
    placement = getattr(element, 'ObjectPlacement', None)
    if placement is None or not placement.is_a('IfcLocalPlacement'):
        return None
    rel = placement.RelativePlacement
    if rel is None or not rel.is_a('IfcAxis2Placement3D'):
        return None
    loc = rel.Location
    if loc is None:
        return None
    coords = loc.Coordinates
    ox, oy = float(coords[0]), float(coords[1])

    axis = rel.Axis
    if axis is not None and len(axis.DirectionRatios) >= 2:
        dx = float(axis.DirectionRatios[0])
        dy = float(axis.DirectionRatios[1])
        norm = math.hypot(dx, dy)
        if norm > 0.0:
            dx, dy = dx / norm, dy / norm
        else:
            dx, dy = 1.0, 0.0
    else:
        dx, dy = 1.0, 0.0

    return ox, oy, dx, dy


def _get_profile_dims(element):
    """IfcProduct の体ジオメトリから断面寸法 (width, height, length) を返す。

    Body 表現の IfcExtrudedAreaSolid + IfcRectangleProfileDef を解析する。
    見つからない場合は None を返す。
    """
    rep = getattr(element, 'Representation', None)
    if rep is None:
        return None
    for shape_rep in rep.Representations:
        if shape_rep.RepresentationIdentifier != 'Body':
            continue
        for item in shape_rep.Items:
            if not item.is_a('IfcExtrudedAreaSolid'):
                continue
            area = item.SweptArea
            if not area.is_a('IfcRectangleProfileDef'):
                continue
            return float(area.XDim), float(area.YDim), float(item.Depth)
    return None


def _get_material_name(element):
    """IfcProduct に関連付けられた材種名を返す。見つからない場合は空文字。"""
    for rel in getattr(element, 'HasAssociations', ()):
        if not rel.is_a('IfcRelAssociatesMaterial'):
            continue
        mat = rel.RelatingMaterial
        if mat.is_a('IfcMaterial'):
            return mat.Name or ''
        if mat.is_a('IfcMaterialList') and mat.Materials:
            return mat.Materials[0].Name or ''
        if mat.is_a('IfcMaterialLayerSetUsage'):
            layers = mat.ForLayerSet.MaterialLayers
            if layers:
                return layers[0].Material.Name or ''
    return ''


def make_member_id(width, height, material):
    """断面寸法と材種名から構造材 ID 文字列を生成する。

    例: make_member_id(120, 180, '杉対称異等級集成材E105-F355')
        → '120×180 - 杉対称異等級集成材E105-F355'
    """
    w = int(round(width))
    h = int(round(height))
    return f'{w}×{h} - {material}' if material else f'{w}×{h}'


def _snap_endpoints(beams, tolerance=_JOIN_TOLERANCE):
    """負け部材の端点を勝ち部材の中心線にスナップして部材結合を実現する。

    IFC では仕口の勝ち・負けを考慮した実寸ジオメトリが格納されており、
    負け側の端点は勝ち部材の面に接した位置（中心線からずれた位置）にある。
    この関数は各端点から直交方向に最近の部材中心線を探し、
    端点を中心線まで延伸して VectorWorks の自動結合が機能する状態にする。

    Parameters
    ----------
    beams : list of dict
        keys: x1, y1, x2, y2, dx, dy, half_width
        (dx, dy は start→end の単位方向ベクトル、half_width は XDim/2)
    tolerance : float
        端点と交差部材中心線のずれ許容量 [mm]

    Returns
    -------
    list of dict
        keys: x1, y1, x2, y2 (スナップ後座標),
              start_join_offset, end_join_offset
        join_offset はその端点がスナップされた相手部材のハーフ幅 (mm)。
        スナップされなかった端点では None。
    """
    # (origin_x, origin_y, dir_x, dir_y, half_width, span_length) のリスト
    segs = [
        (b['x1'], b['y1'], b['dx'], b['dy'],
         b['half_width'], math.hypot(b['x2'] - b['x1'], b['y2'] - b['y1']))
        for b in beams
    ]

    def try_snap(px, py, adx, ady, extend_forward, others):
        """端点 (px, py) を直交する最近部材の中心線にスナップする。

        extend_forward=True  → 終端 (x2,y2) を前方 (+adx,+ady) へ延伸
        extend_forward=False → 始端 (x1,y1) を後方 (-adx,-ady) へ延伸

        Returns
        -------
        (new_x, new_y, winner_half_width)
            スナップしなかった場合は winner_half_width=None
        """
        ext_x = adx if extend_forward else -adx
        ext_y = ady if extend_forward else -ady
        best_t, snapped, winner_hw = float('inf'), None, None

        for ox, oy, odx, ody, ohw, other_len in others:
            # 直交チェック (dot ≈ 0)
            if abs(adx * odx + ady * ody) > 0.1:
                continue
            # 2 直線の交点パラメータを解く:
            #   (px,py) + t*(ext_x,ext_y) = (ox,oy) + s*(odx,ody)
            denom = ext_x * ody - ext_y * odx
            if abs(denom) < 1e-9:
                continue
            t = ((ox - px) * ody - (oy - py) * odx) / denom
            s = ((ox - px) * ext_y - (oy - py) * ext_x) / denom
            # t: 延伸量。負け端点は勝ち部材の面に接しているので 0〜ohw+tolerance
            if t < -1.0 or t > ohw + tolerance:
                continue
            # s: 交点が勝ち部材のスパン内（±ohw 余裕を含む）
            if s < -ohw - tolerance or s > other_len + ohw + tolerance:
                continue
            if t < best_t:
                best_t = t
                snapped = (px + t * ext_x, py + t * ext_y)
                winner_hw = ohw

        if snapped is None:
            return px, py, None
        return snapped[0], snapped[1], winner_hw

    results = []
    for i, b in enumerate(beams):
        others = segs[:i] + segs[i + 1:]
        nx1, ny1, start_hw = try_snap(b['x1'], b['y1'], b['dx'], b['dy'], False, others)
        nx2, ny2, end_hw = try_snap(b['x2'], b['y2'], b['dx'], b['dy'], True, others)
        results.append({
            'x1': nx1, 'y1': ny1, 'x2': nx2, 'y2': ny2,
            'start_join_offset': start_hw,
            'end_join_offset': end_hw,
        })

    return results


def _draw_member(x1, y1, x2, y2, width, height, member_id, layer_elevation):
    """構造材ツールで 1 本の部材を描画する。

    パスはローカル原点 (0,0,0) から方向ベクトルで定義し、
    CreateCustomObjectPath 後に Move3D で絶対位置へ移動する。
    これは VW 構造材ツールの期待する配置パターンと一致する。
    プラグインが利用できない場合は通常の直線にフォールバックする。
    """
    # パスをローカル座標で作成 (始点=原点、終点=方向×長さ)
    path_h = vs.CreateNurbsCurve(0, 0, 0, False, 1)
    vs.AddVertex3D(path_h, x2 - x1, y2 - y1, 0)

    w = int(round(width))
    h = int(round(height))
    vs.BeginGroup()
    vs.ClosePoly()
    vs.Poly(0, 0, 0, h, w, h, w, 0)
    vs.EndGroup()
    profile_h = vs.LNewObj()

    obj = vs.CreateCustomObjectPath(PLUGIN_NAME, path_h, profile_h)
    if obj != vs.Handle(0):
        # ローカル原点から実際の配置位置へ移動
        vs.ResetOrientation3D()
        vs.Move3D(x1, y1, layer_elevation)
        vs.SetRField(obj, PLUGIN_NAME, 'MemberID', member_id)
        vs.SetRField(obj, PLUGIN_NAME, 'ProfileShape', 'Rectangle')
        vs.SetRField(obj, PLUGIN_NAME, 'MajorBreadth', str(w))
        vs.SetRField(obj, PLUGIN_NAME, 'MajorDepth', str(h))
        vs.SetRField(obj, PLUGIN_NAME, 'B', str(w))
        vs.SetRField(obj, PLUGIN_NAME, 'D', str(h))
        vs.SetRField(obj, PLUGIN_NAME, 'MemberType', '2')
        vs.SetRField(obj, PLUGIN_NAME, 'StructuralUse', '1')
        vs.SetRField(obj, PLUGIN_NAME, 'AxisAlign', '1')
        vs.SetRField(obj, PLUGIN_NAME, 'EndCondition', '3')
        vs.SetRField(obj, PLUGIN_NAME, 'StartCondition', '3')
        vs.SetRField(obj, PLUGIN_NAME, 'ProfileSeries', 'AISC (Inch)')
        vs.ResetObject(obj)
    else:
        # フォールバック: 通常の直線
        vs.MoveTo(x1, y1)
        vs.LineTo(x2, y2)
        vs.LNewObj()


def import_members(ifc_file):
    """IFC の横架材 (IfcBeam / IfcMember) を各階の横架材天端レイヤに描画し、配置数を返す。

    配置座標は通り芯と同じグリッド中心オフセットで補正する。
    最上階（屋根）には横架材天端レイヤが存在しないため対象外とする。
    """
    _, center_x, center_y = resolve_lines(ifc_file)

    storeys = sorted(
        [s for s in ifc_file.by_type('IfcBuildingStorey')
         if (s.Name or '').upper().endswith('FL')],
        key=lambda s: float(s.Elevation or 0.0),
    )
    if not storeys:
        return 0

    top_idx = len(storeys) - 1
    count = 0

    for i, storey in enumerate(storeys):
        is_top = (i == top_idx)
        prefix = layer_prefix_for(i, is_top)
        # 最上階は横架材天端レイヤがなく軒高レイヤに描画する
        layer_suffix = LEVEL_EAVES if is_top else LAYER_SUFFIX
        layer_name = f'{prefix}-{layer_suffix}'

        if vs.GetObject(layer_name) == vs.Handle(0):
            continue
        vs.Layer(layer_name)

        storey_elevation = float(storey.Elevation or 0.0)
        if is_top:
            layer_elevation = storey_elevation
        else:
            layer_elevation = storey_elevation + resolve_beam_top_offset(storey)

        # 1st pass: 部材情報を収集
        raw_beams = []
        for rel in storey.ContainsElements:
            for element in rel.RelatedElements:
                if not any(element.is_a(t) for t in _IFC_MEMBER_TYPES):
                    continue
                placement = _get_placement_2d(element)
                if placement is None:
                    continue
                dims = _get_profile_dims(element)
                if dims is None:
                    continue
                ox, oy, dx, dy = placement
                width, height, length = dims
                x1 = ox - center_x
                y1 = oy - center_y
                raw_beams.append({
                    'x1': x1, 'y1': y1,
                    'x2': x1 + dx * length, 'y2': y1 + dy * length,
                    'dx': dx, 'dy': dy,
                    'half_width': width / 2,
                    'width': width, 'height': height,
                    'member_id': make_member_id(width, height, _get_material_name(element)),
                })

        # 2nd pass: 負け端点を勝ち部材の中心線にスナップ
        snapped = _snap_endpoints(raw_beams)

        # 3rd pass: 描画
        for beam, snap in zip(raw_beams, snapped):
            _draw_member(snap['x1'], snap['y1'], snap['x2'], snap['y2'],
                         beam['width'], beam['height'],
                         beam['member_id'], layer_elevation)
            count += 1

    return count
