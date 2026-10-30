"""The backend accepts exactly the structured samples reopened by the real editor."""
import copy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from yantu.document_model import validate_document


FIXTURE = Path(__file__).parent / 'fixtures' / 'document_v2_roundtrip.json'


def test_supported_document_roundtrip_contract():
    content = json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert validate_document(content, for_write=True)[0] == content
    assert validate_document(content, for_editor=True)[0] == content


@pytest.mark.parametrize('mutation', (
    'empty_text', 'empty_quote', 'list_without_paragraph', 'uneven_table',
    'missing_cell_default', 'missing_link_default', 'explicit_empty_content', 'explicit_empty_marks',
))
def test_legacy_shape_may_be_read_but_cannot_be_saved_silently(mutation):
    content = json.loads(FIXTURE.read_text(encoding='utf-8'))
    if mutation == 'empty_text':
        content['content'][0]['content'][0]['text'] = ''
    elif mutation == 'empty_quote':
        content['content'][4]['content'] = []
    elif mutation == 'list_without_paragraph':
        content['content'][2]['content'][0]['content'].pop(0)
    elif mutation == 'uneven_table':
        content['content'][-1]['content'][0]['content'][0]['attrs']['colspan'] = 2
    elif mutation == 'missing_cell_default':
        content['content'][-1]['content'][0]['content'][0]['attrs'].pop('background')
    elif mutation == 'missing_link_default':
        content['content'][1]['content'][2]['marks'][0]['attrs'].pop('target')
    elif mutation == 'explicit_empty_content':
        content['content'][0]['content'] = []
    elif mutation == 'explicit_empty_marks':
        content['content'][0]['content'][0]['marks'] = []
    assert validate_document(content)[0] == content
    with pytest.raises(HTTPException):
        validate_document(content, for_editor=True)
    with pytest.raises(HTTPException):
        validate_document(content, for_write=True)


def test_valid_editor_blocks_in_list_and_nested_table():
    content = json.loads(FIXTURE.read_text(encoding='utf-8'))
    nested = copy.deepcopy(content['content'][4]['content'][0])
    nested['attrs']['id'] = '00000000-0000-4000-8000-000000000100'
    content['content'][2]['content'][0]['content'].append(nested)
    assert validate_document(content, for_write=True)[0] == content
