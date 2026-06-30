"""IFC 読み込み・サニタイズ (ifc.loader) のテスト。vs 非依存。"""
from __future__ import annotations

import os
from unittest.mock import patch

from vectorworks_plugin_import_ifc_homeskz.ifc import loader, open_ifc

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')

_IFC2X3_HEADER = (
    "ISO-10303-21;\n"
    "HEADER;\n"
    "FILE_DESCRIPTION((''),'2;1');\n"
    "FILE_NAME('x','t',(''),(''),'','','');\n"
    "FILE_SCHEMA(('IFC2X3'));\n"
    "ENDSEC;\n"
    "DATA;\n"
)


class TestVersionGate:
    def test_release_tuple_parses_release_part(self) -> None:
        assert loader._release_tuple('0.8.4.post1') == (0, 8, 4)
        assert loader._release_tuple('0.8.5') == (0, 8, 5)
        assert loader._release_tuple('0.8.5.dev0') == (0, 8, 5)
        assert loader._release_tuple('v0.8') is None
        assert loader._release_tuple('unknown') is None

    def test_needs_sanitize_for_old_version(self) -> None:
        with patch.object(loader.ifcopenshell, 'version', '0.8.4.post1'):
            assert loader._needs_sanitize() is True

    def test_no_sanitize_for_new_version(self) -> None:
        with patch.object(loader.ifcopenshell, 'version', '0.8.5'):
            assert loader._needs_sanitize() is False

    def test_needs_sanitize_when_version_unparseable(self) -> None:
        # 判定できない場合は安全側(サニタイズする)
        with patch.object(loader.ifcopenshell, 'version', 'mystery'):
            assert loader._needs_sanitize() is True

    def test_open_ifc_skips_sanitize_on_new_version(self) -> None:
        """新しい ifcopenshell ではファイルを読まず ifcopenshell.open に委ねる。"""
        path = os.path.join(FIXTURES_DIR, '伏図次郎【2階】.ifc')
        with patch.object(loader.ifcopenshell, 'version', '0.8.5'), \
                patch.object(loader.ifcopenshell, 'open') as mock_open, \
                patch.object(loader, '_sanitize') as mock_sanitize:
            open_ifc(path)
        mock_open.assert_called_once_with(path)
        mock_sanitize.assert_not_called()

    def test_open_ifc_sanitizes_on_old_version(self) -> None:
        """古い ifcopenshell では from_string 経由でサニタイズ済みを開く。"""
        path = os.path.join(FIXTURES_DIR, '伏図次郎【2階】.ifc')
        with patch.object(loader.ifcopenshell, 'version', '0.8.4.post1'), \
                patch.object(loader.ifcopenshell, 'open') as mock_open, \
                patch.object(loader.ifcopenshell.file, 'from_string') as mock_from_string:
            open_ifc(path)
        mock_from_string.assert_called_once()
        mock_open.assert_not_called()


class TestSanitize:
    def test_strips_invalid_footing_type_in_ifc2x3(self) -> None:
        text = (
            _IFC2X3_HEADER
            + "#1= IFCFOOTING('g',$,'基礎梁:1',$,$,$,$,$,.FOOTING_BEAM.);\n"
            + "#2= IFCFOOTINGTYPE('t',$,'FG1',$,$,$,$,$,$);\n"
            + "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        sanitized = loader._sanitize(text)
        assert sanitized is not None
        assert 'IFCFOOTINGTYPE' not in sanitized
        # 正常な IFCFOOTING は残る
        assert 'IFCFOOTING(' in sanitized

    def test_returns_none_when_no_invalid_entities(self) -> None:
        text = (
            _IFC2X3_HEADER
            + "#1= IFCFOOTING('g',$,'基礎梁:1',$,$,$,$,$,.FOOTING_BEAM.);\n"
            + "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        assert loader._sanitize(text) is None

    def test_returns_none_for_non_ifc2x3(self) -> None:
        text = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
            + "#2= IFCFOOTINGTYPE('t',$,'FG1',$,$,$,$,$,$);\n"
            + "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        # IFC4 では IfcFootingType は正当なので触らない
        assert loader._sanitize(text) is None

    def test_instance_regex_matches_only_target(self) -> None:
        line = "#5= IFCFOOTINGTYPE('t',#11,'FG1',$,$,(#6),$,$,$);"
        assert loader._INSTANCE_RE.search(line) is not None
        assert loader._INSTANCE_RE.search("#5= IFCFOOTING('g',$,'x',$,$,$,$,$,$);") is None


class TestOpenIfc:
    def test_loads_all_footings_from_fixture(self) -> None:
        """サニタイズにより古い ifcopenshell でも基礎が取りこぼされない。"""
        ifc = open_ifc(os.path.join(FIXTURES_DIR, '伏図次郎【2階】.ifc'))
        # 不正エンティティで取りこぼすと 1 件しか読めない。サニタイズ後は多数。
        assert len(ifc.by_type('IfcFooting')) > 50

    def test_falls_back_for_missing_file_on_old_version(self) -> None:
        # サニタイズ対象バージョンでも、読み込みに失敗したら ifcopenshell.open に委ねる
        # (OSError を握りつぶし sanitized=None としてフォールバックする経路)。
        missing = os.path.join(FIXTURES_DIR, '__does_not_exist__.ifc')
        with patch.object(loader.ifcopenshell, 'version', '0.8.4.post1'):
            try:
                open_ifc(missing)
            except Exception:
                pass
            else:  # pragma: no cover - 例外が出ない場合のみ
                raise AssertionError('存在しないファイルで例外が送出されるはず')
