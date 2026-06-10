"""命令セット (document) スキーマ検証のテスト。vs 非依存。"""
import json

import pytest

from vectorworks_plugin_import_ifc_homeskz.document import (
    DOCUMENT_VERSION,
    DocumentValidationError,
    validate_document,
)


def make_valid_document():
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
            {
                'label': 'X1', 'layer': '共通',
                'class': '01作図-01線-01基準線-01通り芯-X通り',
                'start': [0.0, -1000.0], 'end': [0.0, 1000.0],
            },
        ],
        'members': [
            {
                'layer': '1-横架材天端', 'member_id': '120×180 - 杉',
                'start': [0.0, 0.0], 'end': [3000.0, 0.0],
                'width': 120.0, 'height': 180.0, 'elevation': 425.0,
            },
        ],
    }


class TestValidateDocument:
    def test_valid_document_passes(self):
        document = make_valid_document()
        assert validate_document(document) is document

    def test_valid_document_survives_json_roundtrip(self):
        document = json.loads(json.dumps(make_valid_document()))
        assert validate_document(document) is document

    def test_empty_command_lists_pass(self):
        document = {'version': DOCUMENT_VERSION, 'stories': [], 'grids': [], 'members': []}
        validate_document(document)

    def test_rejects_non_dict(self):
        with pytest.raises(DocumentValidationError):
            validate_document([])

    def test_rejects_unsupported_version(self):
        document = make_valid_document()
        document['version'] = 999
        with pytest.raises(DocumentValidationError, match='バージョン'):
            validate_document(document)

    def test_rejects_missing_version(self):
        document = make_valid_document()
        del document['version']
        with pytest.raises(DocumentValidationError):
            validate_document(document)

    @pytest.mark.parametrize('key', ['stories', 'grids', 'members'])
    def test_rejects_missing_command_list(self, key):
        document = make_valid_document()
        del document[key]
        with pytest.raises(DocumentValidationError):
            validate_document(document)

    def test_rejects_story_with_empty_suffix(self):
        # 空文字 suffix は VW 2026 で 2 回目以降の CreateStory が失敗する
        document = make_valid_document()
        document['stories'][0]['suffix'] = ''
        with pytest.raises(DocumentValidationError, match='suffix'):
            validate_document(document)

    def test_rejects_story_with_non_numeric_elevation(self):
        document = make_valid_document()
        document['stories'][0]['elevation'] = '473'
        with pytest.raises(DocumentValidationError, match='elevation'):
            validate_document(document)

    def test_rejects_level_without_layer(self):
        document = make_valid_document()
        del document['stories'][0]['levels'][0]['layer']
        with pytest.raises(DocumentValidationError, match='layer'):
            validate_document(document)

    def test_rejects_grid_without_class(self):
        document = make_valid_document()
        del document['grids'][0]['class']
        with pytest.raises(DocumentValidationError, match='class'):
            validate_document(document)

    def test_rejects_grid_with_bad_point(self):
        document = make_valid_document()
        document['grids'][0]['start'] = [0.0]
        with pytest.raises(DocumentValidationError, match='start'):
            validate_document(document)

    def test_rejects_member_without_dimension(self):
        document = make_valid_document()
        del document['members'][0]['width']
        with pytest.raises(DocumentValidationError, match='width'):
            validate_document(document)

    def test_rejects_member_with_non_string_id(self):
        document = make_valid_document()
        document['members'][0]['member_id'] = 120
        with pytest.raises(DocumentValidationError, match='member_id'):
            validate_document(document)
