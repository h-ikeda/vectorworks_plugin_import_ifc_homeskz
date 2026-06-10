"""描画フェーズの入口 execute_document() のテスト。"""
import importlib
from unittest.mock import MagicMock, patch

import pytest

from vectorworks_plugin_import_ifc_homeskz.document import (
    DOCUMENT_VERSION,
    DocumentValidationError,
)


def _make_stateful_vs_mock():
    """ストーリ・レイヤ作成を追跡するステートフルな vs モック。"""
    vs_mock = MagicMock()
    null_handle = object()
    vs_mock.Handle.return_value = null_handle

    created = set()
    template_counter = [0]

    def get_obj(name):
        if name in created:
            return 'HANDLE_' + name
        return null_handle

    def create_story(name, suffix):
        created.add(name)
        return True

    def create_layer(name, layer_type):
        created.add(name)
        return 'HANDLE_' + name

    def create_level_template(layer_name, scale, level_type, elev, wall_h):
        idx = template_counter[0]
        template_counter[0] += 1
        # AddLevelFromTemplate はレイヤを自動生成する
        created.add(layer_name)
        return (True, idx)

    vs_mock.GetObject.side_effect = get_obj
    vs_mock.CreateStory.side_effect = create_story
    vs_mock.CreateLayer.side_effect = create_layer
    vs_mock.CreateLevelTemplateN.side_effect = create_level_template
    vs_mock.AddLevelFromTemplate.return_value = True
    vs_mock.GetLayerForStory.return_value = 'HANDLE_template_layer'
    vs_mock.LNewObj.return_value = object()
    vs_mock.CreateCustomObjectPath.return_value = object()
    return vs_mock


def _run_execute_document(vs_mock, document):
    with patch.dict('sys.modules', {'vs': vs_mock}):
        import vectorworks_plugin_import_ifc_homeskz.vw as vw
        import vectorworks_plugin_import_ifc_homeskz.vw.grid as vw_grid
        import vectorworks_plugin_import_ifc_homeskz.vw.member as vw_member
        import vectorworks_plugin_import_ifc_homeskz.vw.story as vw_story
        importlib.reload(vw_grid)
        importlib.reload(vw_member)
        importlib.reload(vw_story)
        importlib.reload(vw)
        return vw.execute_document(document)


def make_document():
    return {
        'version': DOCUMENT_VERSION,
        'stories': [
            {
                'name': '1階', 'suffix': '1', 'elevation': 473.0,
                'levels': [
                    {'type': 'FL', 'offset': 0.0, 'layer': '1-FL'},
                    {'type': '横架材天端', 'offset': -48.0, 'layer': '1-横架材天端'},
                ],
            },
            {
                'name': '屋根', 'suffix': 'R', 'elevation': 5973.0,
                'levels': [
                    {'type': '軒高', 'offset': 0.0, 'layer': 'R-軒高'},
                ],
            },
        ],
        'grids': [
            {'label': 'X1', 'layer': '共通', 'class': 'X通りクラス',
             'start': [0.0, -1000.0], 'end': [0.0, 1000.0]},
        ],
        'members': [
            {'layer': '1-横架材天端', 'member_id': '120×180', 'start': [0.0, 0.0],
             'end': [3000.0, 0.0], 'width': 120.0, 'height': 180.0, 'elevation': 425.0},
        ],
    }


class TestExecuteDocument:
    def test_executes_all_commands_and_returns_counts(self):
        vs_mock = _make_stateful_vs_mock()
        counts = _run_execute_document(vs_mock, make_document())
        assert counts == {'stories': 2, 'grids': 1, 'members': 1}

    def test_empty_document_returns_zero_counts(self):
        vs_mock = _make_stateful_vs_mock()
        document = {'version': DOCUMENT_VERSION, 'stories': [], 'grids': [], 'members': []}
        counts = _run_execute_document(vs_mock, document)
        assert counts == {'stories': 0, 'grids': 0, 'members': 0}

    def test_rejects_unsupported_version_before_drawing(self):
        vs_mock = _make_stateful_vs_mock()
        document = make_document()
        document['version'] = 999

        with pytest.raises(DocumentValidationError):
            _run_execute_document(vs_mock, document)

        vs_mock.CreateStory.assert_not_called()
        vs_mock.CreateCustomObjectPath.assert_not_called()

    def test_rejects_invalid_command_before_drawing(self):
        vs_mock = _make_stateful_vs_mock()
        document = make_document()
        del document['grids'][0]['class']

        with pytest.raises(DocumentValidationError):
            _run_execute_document(vs_mock, document)

        vs_mock.CreateStory.assert_not_called()
