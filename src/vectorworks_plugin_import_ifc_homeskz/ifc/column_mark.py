"""断面記号(柱束伏図記号 PIO)の命令の組み立て。vs 非依存。

姉妹プロジェクト vectorworks-plugin-column-under-mark のカスタム PIO
「柱束伏図記号」(指定レイヤ・クラスの構造用途 4/5 の構造材を検索し、断面スタイルでは
柱×・小屋束/ を実断面に合わせて各位置に描くポイントオブジェクト)を配置する命令
(column_mark 命令)を組み立てる。

柱・小屋束は span(``{from}to{to}-柱``)ごとのレイヤに配置される(``ifc/column.py``)。
実在する span レイヤごとに **断面記号** PIO を 1 つ重ね、そのレイヤ自身を検索対象・配置
先(``target_class`` は空=全クラス)にして、記号スタイル=断面(``MarkStyle=断面``)・
作図クラス=極細実線(``01作図-01線-02実線-01極細線``)で描く。各伏図はその span レイヤを
表示すると柱・小屋束の断面記号も併せて載る(span レイヤの表示可否は ``ifc/sheet.py`` が
切断レベルで決める)。

母屋伏図に小屋束を平面記号(伏図記号=○)で示す従来の小屋束記号、および直下階の柱を
記号化する下階柱記号は、span 方式では柱の表示自体をレイヤの切断レベルで制御するため
役割が変わる。母屋伏図向けの小屋束伏図記号は span 方式への移行後に別途対応する予定で、
現状このモジュールは断面記号のみを生成する。判断は柱の span レイヤ(=column 命令)から
決まり、IFC のジオメトリは参照しない。
"""
from __future__ import annotations

from ..document import ColumnCommand, ColumnMarkCommand
from .column import collect_column_spans

# 記号の既定サイズ (mm)。柱束伏図記号 PIO の MarkSize に渡す。姉妹プロジェクトの
# 既定値 (core/mark.py の DEFAULT_MARK_SIZE=300mm) に合わせる。
DEFAULT_MARK_SIZE = 300.0
# 記号スタイル(柱束伏図記号 PIO の MarkStyle パラメータに渡す値)。姉妹プロジェクト
# vectorworks-plugin-column-under-mark の normalize_style が '断面'/'section' を断面記号、
# それ以外(空文字含む)を平面記号として解釈する。span レイヤに重ねる断面記号は断面記号
# (実断面に合わせた柱×・小屋束/)。母屋伏図に小屋束を平面記号(伏図記号)で示す機能は
# span 方式への移行後に別途対応する(現状は断面記号のみ生成する)。
MARK_STYLE_SECTION = '断面'
# 断面記号(各 span 柱レイヤに重ねる柱束伏図記号 PIO)の作図クラス。極細の実線で
# 実断面の対角線を描く。
SECTION_MARK_CLASS = '01作図-01線-02実線-01極細線'
# PIO の挿入点。記号は検索した柱のワールド位置に描かれ挿入点には依存しないため
# 原点でよい(座標はセンタリング済み)。
INSERTION_POINT: list[float] = [0.0, 0.0]


def build_column_mark_commands(
    columns: list[ColumnCommand],
) -> list[ColumnMarkCommand]:
    """断面記号(column_mark 命令)を span 柱レイヤごとに組み立てて返す。

    柱・小屋束は span(``{from}to{to}-柱``)ごとのレイヤに配置される。各 span レイヤに、
    そのレイヤ自身を検索対象とする柱束伏図記号 PIO を重ね、断面スタイルで実断面に合わせた
    記号(柱×・小屋束/)を描く。対象クラスは絞らず(空=全クラス)、そのレイヤの構造用途
    4/5 の構造材すべてを記号化する。伏図はその span レイヤを表示すると柱と併せて断面記号も
    載る(span レイヤの表示可否は sheet が切断レベルで決める)。

    母屋伏図に小屋束を平面記号(伏図記号)で示す機能は span 方式への移行後に別途対応する
    ため、ここでは生成しない(現状は断面記号のみ)。柱が無ければ空リストを返す。
    """
    commands: list[ColumnMarkCommand] = []
    for _frm, _to, layer in collect_column_spans(columns):
        commands.append({
            'layer': layer,
            'class': SECTION_MARK_CLASS,
            'target_layer': layer,
            'target_class': '',
            'size': DEFAULT_MARK_SIZE,
            'style': MARK_STYLE_SECTION,
            'position': list(INSERTION_POINT),
        })
    return commands
