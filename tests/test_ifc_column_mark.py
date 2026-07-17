"""解析フェーズ (ifc.column_mark) のテスト。vs 非依存。

柱・小屋束は span(``{from}to{to}-柱``)ごとのレイヤに配置される。断面記号
(柱束伏図記号 PIO・記号スタイル=断面)が、実在する span レイヤごとに 1 つずつ、
そのレイヤ自身を検索対象・配置先(target_class は空=全クラス)にして組み立てられる
ことを検証する。母屋伏図の小屋束伏図記号(平面記号)は span 方式移行後に別途対応する
ため、ここでは生成されない。
"""
from __future__ import annotations

import json
from typing import cast

from vectorworks_plugin_import_ifc_homeskz.document import ColumnCommand
from vectorworks_plugin_import_ifc_homeskz.ifc.column_mark import (
    DEFAULT_MARK_SIZE,
    MARK_STYLE_SECTION,
    SECTION_MARK_CLASS,
    build_column_mark_commands,
)


def _column(layer: str) -> ColumnCommand:
    """テスト用の最小 column 命令(build_column_mark_commands は layer だけを見る)。"""
    return cast(ColumnCommand, {'layer': layer})


class TestBuildColumnMarkCommands:
    def test_no_columns_returns_empty(self) -> None:
        assert build_column_mark_commands([]) == []

    def test_section_mark_per_span_layer(self) -> None:
        # 実在する span レイヤごとに 1 つの断面記号。並びは (from, to) 昇順。
        columns = [
            _column('2to3-柱'), _column('1to2-柱'),
            _column('2to2.5-柱'), _column('2to3-柱'), _column('3to3.5-柱'),
        ]
        commands = build_column_mark_commands(columns)
        assert commands == [
            {
                'layer': '1to2-柱', 'class': SECTION_MARK_CLASS,
                'target_layer': '1to2-柱', 'target_class': '',
                'size': DEFAULT_MARK_SIZE, 'style': MARK_STYLE_SECTION,
                'position': [0.0, 0.0],
            },
            {
                'layer': '2to2.5-柱', 'class': SECTION_MARK_CLASS,
                'target_layer': '2to2.5-柱', 'target_class': '',
                'size': DEFAULT_MARK_SIZE, 'style': MARK_STYLE_SECTION,
                'position': [0.0, 0.0],
            },
            {
                'layer': '2to3-柱', 'class': SECTION_MARK_CLASS,
                'target_layer': '2to3-柱', 'target_class': '',
                'size': DEFAULT_MARK_SIZE, 'style': MARK_STYLE_SECTION,
                'position': [0.0, 0.0],
            },
            {
                'layer': '3to3.5-柱', 'class': SECTION_MARK_CLASS,
                'target_layer': '3to3.5-柱', 'target_class': '',
                'size': DEFAULT_MARK_SIZE, 'style': MARK_STYLE_SECTION,
                'position': [0.0, 0.0],
            },
        ]

    def test_style_is_section_and_class_is_thin_line(self) -> None:
        commands = build_column_mark_commands([_column('1to2-柱')])
        assert len(commands) == 1
        assert commands[0]['style'] == MARK_STYLE_SECTION
        assert commands[0]['class'] == SECTION_MARK_CLASS

    def test_commands_are_json_serializable(self) -> None:
        commands = build_column_mark_commands(
            [_column('1to2-柱'), _column('2to2.5-柱')])
        assert json.loads(json.dumps(commands)) == commands
