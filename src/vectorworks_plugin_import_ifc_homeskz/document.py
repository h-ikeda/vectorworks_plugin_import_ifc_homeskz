"""JSON 命令セット（ドキュメント）のスキーマ定義と検証。

命令セットは IFC 解析フェーズ（``ifc`` パッケージ）が生成し、
描画フェーズ（``vw`` パッケージ）が消費する JSON 直列化可能な dict。
このモジュールは vs にも ifcopenshell にも依存しない。

スキーマ (version 1):

    {
        "version": 1,
        "stories": [
            {
                "name": "1階",            # VectorWorks のストーリ名
                "suffix": "1",            # CreateStory の suffix（非空必須）
                "elevation": 473.0,       # ストーリ高さ (mm)
                "levels": [
                    {
                        "type": "FL",         # ストーリレベルタイプ名
                        "offset": 0.0,        # ストーリ基準からのオフセット (mm)
                        "layer": "1-FL"       # 生成するデザインレイヤ名
                    }
                ]
            }
        ],
        "grids": [
            {
                "label": "X1",            # 通り芯の軸名
                "layer": "共通",           # 配置先デザインレイヤ名
                "class": "01作図-...",     # 割り当てるクラス名
                "start": [x1, y1],        # 始点 (mm, センタリング済み)
                "end": [x2, y2]           # 終点 (mm, センタリング済み)
            }
        ],
        "members": [
            {
                "layer": "1-横架材天端",   # 配置先デザインレイヤ名（既存のみ・なければスキップ）
                "member_id": "120×180 - 杉...",  # 構造材 ID
                "start": [x1, y1],        # 始点 (mm, センタリング済み)
                "end": [x2, y2],          # 終点 (mm, センタリング済み)
                "width": 120.0,           # 断面幅 (mm)
                "height": 180.0,          # 断面背 (mm)
                "elevation": 425.0        # 配置 Z 高さ (mm, 絶対値)
            }
        ]
    }
"""

DOCUMENT_VERSION = 1


class DocumentValidationError(ValueError):
    """命令セットがスキーマに適合しない場合に送出される。"""


def _require(condition, message):
    if not condition:
        raise DocumentValidationError(message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_point(value):
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(_is_number(c) for c in value)
    )


def _validate_level(index, level_index, level):
    where = f'stories[{index}].levels[{level_index}]'
    _require(isinstance(level, dict), f'{where} は dict である必要があります')
    _require(isinstance(level.get('type'), str) and level['type'],
             f'{where}.type は非空文字列である必要があります')
    _require(_is_number(level.get('offset')), f'{where}.offset は数値である必要があります')
    _require(isinstance(level.get('layer'), str) and level['layer'],
             f'{where}.layer は非空文字列である必要があります')


def _validate_story(index, command):
    where = f'stories[{index}]'
    _require(isinstance(command, dict), f'{where} は dict である必要があります')
    _require(isinstance(command.get('name'), str) and command['name'],
             f'{where}.name は非空文字列である必要があります')
    # 空文字 suffix は VW 2026 で 2 回目以降の CreateStory が失敗するため不可
    _require(isinstance(command.get('suffix'), str) and command['suffix'],
             f'{where}.suffix は非空文字列である必要があります')
    _require(_is_number(command.get('elevation')),
             f'{where}.elevation は数値である必要があります')
    _require(isinstance(command.get('levels'), list),
             f'{where}.levels はリストである必要があります')
    for j, level in enumerate(command['levels']):
        _validate_level(index, j, level)


def _validate_grid(index, command):
    where = f'grids[{index}]'
    _require(isinstance(command, dict), f'{where} は dict である必要があります')
    _require(isinstance(command.get('label'), str),
             f'{where}.label は文字列である必要があります')
    _require(isinstance(command.get('layer'), str) and command['layer'],
             f'{where}.layer は非空文字列である必要があります')
    _require(isinstance(command.get('class'), str) and command['class'],
             f'{where}.class は非空文字列である必要があります')
    _require(_is_point(command.get('start')),
             f'{where}.start は [x, y] の数値ペアである必要があります')
    _require(_is_point(command.get('end')),
             f'{where}.end は [x, y] の数値ペアである必要があります')


def _validate_member(index, command):
    where = f'members[{index}]'
    _require(isinstance(command, dict), f'{where} は dict である必要があります')
    _require(isinstance(command.get('layer'), str) and command['layer'],
             f'{where}.layer は非空文字列である必要があります')
    _require(isinstance(command.get('member_id'), str),
             f'{where}.member_id は文字列である必要があります')
    _require(_is_point(command.get('start')),
             f'{where}.start は [x, y] の数値ペアである必要があります')
    _require(_is_point(command.get('end')),
             f'{where}.end は [x, y] の数値ペアである必要があります')
    for key in ('width', 'height', 'elevation'):
        _require(_is_number(command.get(key)),
                 f'{where}.{key} は数値である必要があります')


def validate_document(document):
    """命令セットを検証し、不正な場合は DocumentValidationError を送出する。"""
    _require(isinstance(document, dict), '命令セットは dict である必要があります')
    _require(document.get('version') == DOCUMENT_VERSION,
             f'未対応の命令セットバージョンです: {document.get("version")!r}')
    for key in ('stories', 'grids', 'members'):
        _require(isinstance(document.get(key), list),
                 f'"{key}" はリストである必要があります')
    for i, command in enumerate(document['stories']):
        _validate_story(i, command)
    for i, command in enumerate(document['grids']):
        _validate_grid(i, command)
    for i, command in enumerate(document['members']):
        _validate_member(i, command)
    return document
