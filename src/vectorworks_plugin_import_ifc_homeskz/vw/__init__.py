"""フェーズ2: VectorWorks 描画。

JSON 命令セット（``document.py`` のスキーマ参照）に従って vs モジュールで
実際の描画を行う。このパッケージだけが vs に依存し、IFC や ifcopenshell の
知識は持たない。
"""
from ..document import validate_document
from .grid import execute_grids
from .member import execute_members
from .story import execute_stories

__all__ = ['execute_document', 'execute_grids', 'execute_members', 'execute_stories']


def execute_document(document):
    """命令セットを検証し、ストーリ → 通り芯 → 構造材の順で描画する。

    Returns: {'stories': int, 'grids': int, 'members': int} 各命令の実行数。
    """
    validate_document(document)
    return {
        'stories': execute_stories(document['stories']),
        'grids': execute_grids(document['grids']),
        'members': execute_members(document['members']),
    }
