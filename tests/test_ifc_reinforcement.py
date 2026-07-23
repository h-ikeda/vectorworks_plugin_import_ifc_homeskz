"""解析フェーズ (ifc.reinforcement) のテスト。

配筋仕様のパース(鋼種除去・脚数固定・方向分割)と、立上り/底盤の配筋(レコード用
文字列)の組み立てを検証する。実 IFC フィクスチャは vs 非依存でロードする。
"""
from __future__ import annotations

from typing import Any

from vectorworks_plugin_import_ifc_homeskz.ifc import reinforcement as reinf

from tests.conftest import load_fixture_ifc


class TestStripGrade:
    def test_strips_underscore_grade(self) -> None:
        assert reinf._strip_grade('SD295_1-D13') == '1-D13'

    def test_strips_hyphen_grade(self) -> None:
        assert reinf._strip_grade('SD295-D13@200') == 'D13@200'

    def test_keeps_slab_direction_separator(self) -> None:
        # 鋼種だけ落とし、方向区切りの '_' は残す
        assert reinf._strip_grade('SD295_D13@300_D13@300') == 'D13@300_D13@300'

    def test_leaves_count_prefixed_value(self) -> None:
        # 数字始まり(本数)は鋼種でないため触らない
        assert reinf._strip_grade('2-D13') == '2-D13'

    def test_empty_stays_empty(self) -> None:
        assert reinf._strip_grade('') == ''


class TestForceSingleLeg:
    def test_keeps_single_leg(self) -> None:
        assert reinf._force_single_leg('1-D10@300') == '1-D10@300'

    def test_forces_single_leg_from_other_count(self) -> None:
        assert reinf._force_single_leg('2-D10@300') == '1-D10@300'

    def test_adds_single_leg_to_bare_spec(self) -> None:
        assert reinf._force_single_leg('D10@300') == '1-D10@300'

    def test_empty_stays_empty(self) -> None:
        assert reinf._force_single_leg('') == ''


class TestSlabDirs:
    def test_two_directions(self) -> None:
        assert reinf._slab_dirs('SD295_D13@175_D13@200') == ('D13@175', 'D13@200')

    def test_single_direction_duplicates(self) -> None:
        assert reinf._slab_dirs('SD295-D13@200') == ('D13@200', 'D13@200')

    def test_empty_is_none(self) -> None:
        assert reinf._slab_dirs('') is None


class _StubProp:
    def __init__(self, name: str, value: str) -> None:
        self.Name = name
        self._value = value

    def is_a(self, kind: str) -> bool:
        return kind == 'IfcPropertySingleValue'

    @property
    def NominalValue(self) -> object:
        prop = self

        class _Wrapped:
            wrappedValue = prop._value
        return _Wrapped()


class _StubPset:
    def __init__(self, props: dict[str, str]) -> None:
        self.Name = reinf.PSET_REINFORCEMENT
        self.HasProperties = [_StubProp(k, v) for k, v in props.items()]

    def is_a(self, kind: str) -> bool:
        return kind == 'IfcPropertySet'


class _StubRel:
    def __init__(self, definition: object) -> None:
        self.RelatingPropertyDefinition = definition

    def is_a(self, kind: str) -> bool:
        return kind == 'IfcRelDefinesByProperties'


class _StubElement:
    def __init__(self, props: dict[str, str] | None) -> None:
        if props is None:
            self.IsDefinedBy: list[object] = []
        else:
            self.IsDefinedBy = [_StubRel(_StubPset(props))]


def _element(props: dict[str, str] | None) -> Any:
    """ifcopenshell 要素を模したスタブ(型注釈は Any = entity_instance 相当)。"""
    return _StubElement(props)


class TestWallReinforcement:
    def test_uses_ifc_values(self) -> None:
        element = _element({
            'TopReinforce': 'SD295_1-D13', 'BottomReinforce': 'SD295_2-D13',
            'ShearReinforce': 'SD295_1-D10@300'})
        assert reinf.wall_reinforcement(element) == {
            'top': '1-D13', 'bottom': '2-D13', 'vertical': '1-D10@300'}

    def test_forces_vertical_single_leg(self) -> None:
        element = _element({'ShearReinforce': 'SD295_2-D10@300'})
        assert reinf.wall_reinforcement(element)['vertical'] == '1-D10@300'

    def test_falls_back_to_defaults_when_absent(self) -> None:
        assert reinf.wall_reinforcement(_element(None)) == {
            'top': '1-D13', 'bottom': '1-D13', 'vertical': '1-D10@250'}


class TestSlabReinforcement:
    def test_maps_short_side_to_smaller_extent_axis(self) -> None:
        # 短辺=Y(extent_y 小) → Y 方向=短辺(@175)・X 方向=長辺(@200)
        element = _element({'TopReinforce': 'SD295_D13@175_D13@200'})
        result = reinf.slab_reinforcement(element, extent_x=4550.0, extent_y=3640.0)
        assert result == {'x': 'D13@200', 'y': 'D13@175'}

    def test_maps_short_side_when_x_is_smaller(self) -> None:
        # 短辺=X(extent_x 小) → X 方向=短辺(@175)・Y 方向=長辺(@200)
        element = _element({'TopReinforce': 'SD295_D13@175_D13@200'})
        result = reinf.slab_reinforcement(element, extent_x=3640.0, extent_y=4550.0)
        assert result == {'x': 'D13@175', 'y': 'D13@200'}

    def test_single_direction_same_both_axes(self) -> None:
        element = _element({'TopReinforce': 'SD295-D13@200'})
        result = reinf.slab_reinforcement(element, extent_x=650.0, extent_y=650.0)
        assert result == {'x': 'D13@200', 'y': 'D13@200'}

    def test_falls_back_to_defaults_when_absent(self) -> None:
        result = reinf.slab_reinforcement(_element(None), 3000.0, 2000.0)
        assert result == {'x': 'D13@150', 'y': 'D13@150'}


class TestWallReinforcementFromFixture:
    def test_wall_reinforcement_reads_real_pset(self) -> None:
        ifc = load_fixture_ifc('伏図次郎【2階】.ifc')
        for element in ifc.by_type('IfcFooting'):
            name = element.Name or ''
            if not name.startswith('基礎梁'):
                continue
            bars = reinf.wall_reinforcement(element)
            # 全立上りに上端主筋・下端主筋・縦筋が入る(既定にフォールバックしても非空)
            assert bars['top'] and bars['bottom'] and bars['vertical']
            assert bars['vertical'].startswith('1-')
            return
        raise AssertionError('基礎梁 の立上りが見つからない')
