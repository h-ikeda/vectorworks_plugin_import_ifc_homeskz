"""基礎(立上り・底盤)の配筋情報の解析。vs 非依存。

配筋を 3D の鉄筋オブジェクトとして描くのではなく、立上り(壁オブジェクト)・
基礎スラブ(スラブオブジェクト)の**レコード(``配筋``)に配筋情報を設定**して、
データタグなどから仕様を参照できるようにする。このモジュールは IFC の
``Pset_Reinforcement`` から配筋仕様を取り出し、レコードのフィールドに入れる文字列
(``WallReinforcementCommand`` / ``SlabReinforcementCommand``)を組み立てる
(描画フェーズ ``vw/footing.py`` がオブジェクトのレコードに設定する)。

- **立上り(基礎梁)→ 上端主筋・下端主筋・縦筋**。``TopReinforce`` / ``BottomReinforce``
  (例 ``SD295_1-D13`` / ``2-D13``)を上端・下端主筋に、``ShearReinforce``
  (例 ``SD295_1-D10@300``)を縦筋にする。鋼種(``SD295_`` / ``SD295-``)の接頭辞は
  除く。縦筋は脚数の接頭辞を常に ``1-``(縦筋 1 本)に固定する(ホームズ君の出力は
  全て縦筋 1 本の前提)。
- **底盤(基礎底盤系)→ X 方向・Y 方向**。``TopReinforce``(例
  ``SD295_D13@300_D13@300``)は IFC 上では**短辺方向・長辺方向**の 2 方向配筋
  (``短辺_長辺``)なので、底盤の平面バウンディングボックスの**短辺方向(=extent の
  小さい軸)・長辺方向(=extent の大きい軸)**からグローバル X・Y 方向へ置き換える。

プロパティが無い(IFC に配筋情報が出力されていない)要素には既定値を使う(立上り=
上下 1-D13・縦筋 1-D10@250、底盤=D13@150 両方向)。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..document import SlabReinforcementCommand, WallReinforcementCommand

if TYPE_CHECKING:
    import ifcopenshell

# 配筋情報を保持するプロパティセット名(ホームズ君 IFC)。
PSET_REINFORCEMENT = 'Pset_Reinforcement'
_PROP_TOP = 'TopReinforce'
_PROP_BOTTOM = 'BottomReinforce'
_PROP_SHEAR = 'ShearReinforce'

# IFC に配筋情報が無い場合の既定値(ユーザー指定)。
DEFAULT_BEAM_TOP = '1-D13'
DEFAULT_BEAM_BOTTOM = '1-D13'
DEFAULT_BEAM_VERTICAL = '1-D10@250'
DEFAULT_SLAB_BAR = 'D13@150'

# 鋼種の接頭辞(例 ``SD295_`` / ``SD295-``)。仕様文字列の先頭からこれを取り除く。
# 先頭が「英字 1〜4 + 数字 + 区切り(``_`` か ``-``)」なら鋼種とみなす。``2-D13`` の
# ように数字始まりは鋼種でないため対象外(先頭が英字でないとマッチしない)。
_GRADE_RE = re.compile(r'^[A-Za-z]{1,4}\d+[_-](.+)$')
# 脚数の接頭辞(``1-`` 等)。縦筋(せん断補強筋)はこの脚数で配置を切り替えるが、
# ホームズ君の出力は全て縦筋 1 本のため、脚数を常に ``1-`` に固定する。
_COUNT_PREFIX_RE = re.compile(r'^\d+\s*-\s*')
# 縦筋に固定する脚数の接頭辞(縦筋 1 本)。
_SINGLE_LEG_PREFIX = '1-'


def _strip_grade(text: str) -> str:
    """鋼種の接頭辞(``SD295_`` / ``SD295-``)を取り除いた仕様文字列を返す。"""
    match = _GRADE_RE.match(text.strip())
    return match.group(1) if match else text.strip()


def _strip_count_prefix(text: str) -> str:
    """本数の接頭辞(``1-`` 等)を取り除く(``1-D10@300`` → ``D10@300``)。"""
    return _COUNT_PREFIX_RE.sub('', text)


def _force_single_leg(text: str) -> str:
    """縦筋の脚数の接頭辞を ``1-``(縦筋 1 本)に固定する。

    ``1-D10@300`` / ``2-D10@300`` / ``D10@300`` はいずれも ``1-D10@300`` になる
    (ホームズ君の出力は全て縦筋 1 本の前提)。空文字は空のまま返す(既定値に委ねる)。
    """
    spec = _strip_count_prefix(text)
    return f'{_SINGLE_LEG_PREFIX}{spec}' if spec else ''


def _reinforcement_pset(element: ifcopenshell.entity_instance) -> dict[str, str]:
    """要素の ``Pset_Reinforcement`` の文字列プロパティを名前→値の dict で返す。

    プロパティセット(``IfcRelDefinesByProperties``)は IFC2X3・IFC4 とも逆方向属性
    ``IsDefinedBy`` から辿れる。該当プロパティセットが無ければ空 dict。
    """
    for rel in getattr(element, 'IsDefinedBy', None) or []:
        if not rel.is_a('IfcRelDefinesByProperties'):
            continue
        definition = rel.RelatingPropertyDefinition
        if not (definition.is_a('IfcPropertySet')
                and definition.Name == PSET_REINFORCEMENT):
            continue
        result: dict[str, str] = {}
        for prop in definition.HasProperties:
            if prop.is_a('IfcPropertySingleValue') and prop.NominalValue is not None:
                value = prop.NominalValue.wrappedValue
                if isinstance(value, str):
                    result[prop.Name] = value
        return result
    return {}


def _slab_dirs(value: str) -> tuple[str, str] | None:
    """底盤の配筋文字列を短辺方向・長辺方向の 2 方向に分ける。空・不正なら None。

    ``SD295_D13@300_D13@300`` は鋼種を除くと ``D13@300_D13@300`` で、``_`` 区切りの
    2 方向(短辺方向 @ 長辺方向)。``SD295-D13@200`` のように 1 方向だけのものは
    両方向を同じ仕様にする。
    """
    rest = _strip_grade(value)
    parts = [part for part in rest.split('_') if part]
    if not parts:
        return None
    short = parts[0]
    long = parts[1] if len(parts) > 1 else parts[0]
    return short, long


def wall_reinforcement(
    element: ifcopenshell.entity_instance,
) -> WallReinforcementCommand:
    """立上り(基礎梁)要素の配筋(上端主筋・下端主筋・縦筋)を返す。

    上下端主筋は ``Pset_Reinforcement`` の値から鋼種の接頭辞を除いた仕様文字列
    (本数の接頭辞は残す。例 ``1-D13`` / ``2-D13``)。縦筋は鋼種を除いたうえで脚数の
    接頭辞を ``1-``(縦筋 1 本)に固定した ``1-D10@300`` 形式にする。プロパティが無い
    (空)場合は既定値(上下 1-D13・縦筋 1-D10@250)を使う。
    """
    reinf = _reinforcement_pset(element)
    top = _strip_grade(reinf.get(_PROP_TOP, '')) or DEFAULT_BEAM_TOP
    bottom = _strip_grade(reinf.get(_PROP_BOTTOM, '')) or DEFAULT_BEAM_BOTTOM
    vertical = (_force_single_leg(_strip_grade(reinf.get(_PROP_SHEAR, '')))
                or DEFAULT_BEAM_VERTICAL)
    return {'top': top, 'bottom': bottom, 'vertical': vertical}


def slab_reinforcement(
    element: ifcopenshell.entity_instance,
    extent_x: float,
    extent_y: float,
) -> SlabReinforcementCommand:
    """底盤要素の配筋を、グローバル X 方向・Y 方向に割り当てて返す。

    IFC の ``TopReinforce`` は**短辺方向・長辺方向**(``短辺_長辺``)の 2 方向配筋。
    底盤の平面バウンディングボックスの extent が小さい軸が短辺方向、大きい軸が
    長辺方向なので、その対応でグローバル X・Y 方向へ割り当てる:

    - extent_x ≤ extent_y のとき X 軸が短辺方向 → X 方向=短辺、Y 方向=長辺。
    - extent_x > extent_y のとき Y 軸が短辺方向 → Y 方向=短辺、X 方向=長辺。

    正方形(extent が等しい)や 1 方向だけの配筋(独立基礎底盤など)は両方向が同じ
    仕様になるため区別は不要。プロパティが無い(空)場合は既定値(D13@150 両方向)。
    """
    dirs = _slab_dirs(_reinforcement_pset(element).get(_PROP_TOP, ''))
    if dirs is None:
        short = long = DEFAULT_SLAB_BAR
    else:
        short, long = dirs
    if extent_x <= extent_y:
        # X 軸の extent が小さい = X が短辺方向
        x_dir, y_dir = short, long
    else:
        x_dir, y_dir = long, short
    return {'x': x_dir, 'y': y_dir}
