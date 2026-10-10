import json

import httpx
import pytest

from yantu.models import Resource, Team
from yantu.plane_client import PlaneClient, PlaneError
from yantu.research_assistant import OllamaResearchAssistant


def team():
    return Team(plane_workspace_slug='lab', plane_project_id='project')


def test_retry_finds_item_on_next_page_without_creating_duplicate():
    calls = []
    def respond(request):
        calls.append(request)
        assert request.method == 'GET'
        if request.url.params.get('cursor') == 'next':
            return httpx.Response(200, json={'results': [{'id': 'remote', 'external_id': 'local', 'external_source': 'yantu'}], 'next_page_results': False})
        return httpx.Response(200, json={'results': [], 'next_page_results': True, 'next_cursor': 'next'})
    client = PlaneClient('http://plane', 'key', httpx.MockTransport(respond))
    assert client.create_work_item(team(), 'title', 'description', 'local') == 'remote'
    assert len(calls) == 2


def test_created_description_uses_installed_plane_html_field_and_escapes():
    def respond(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'results': []})
        body = json.loads(request.content)
        assert body['description_html'] == '<p>&lt;script&gt;<br>正文</p>'
        assert 'description' not in body
        return httpx.Response(409, json={'id': 'existing', 'error': 'external id already exists'})
    client = PlaneClient('http://plane', 'key', httpx.MockTransport(respond))
    assert client.create_work_item(team(), 'title', '<script>\n正文', 'local') == 'existing'


def test_approval_sync_maps_completed_state_and_preserves_target_date():
    def respond(request):
        if request.url.path.endswith('/states/'):
            return httpx.Response(200, json={'results': [{'id': 'done', 'group': 'completed'}, {'id': 'doing', 'group': 'started'}]})
        assert request.method == 'PATCH'
        body = json.loads(request.content)
        assert body['state'] == 'done'
        assert body['target_date'] == '2026-10-03'
        assert body['priority'] == 'high'
        return httpx.Response(200, json={'id': 'remote'})
    client = PlaneClient('http://plane', 'key', httpx.MockTransport(respond))
    client.update_work_item(team(), 'remote', 'title', 'criteria', 'done', 'high', '2026-10-03T08:00:00Z')


def test_bad_pagination_fails_before_creating_remote_task():
    def respond(request):
        assert request.method == 'GET'
        return httpx.Response(200, json={'results': [], 'next_page_results': True, 'next_cursor': 'repeat'})
    client = PlaneClient('http://plane', 'key', httpx.MockTransport(respond))
    with pytest.raises(PlaneError):
        client.create_work_item(team(), 'title', 'description', 'local')


def test_unconfigured_model_returns_actual_cited_passages():
    resource = Resource(id='resource', title='论文阅读', extracted_text='论文阅读应先阅读摘要并记录研究问题。')
    answer = OllamaResearchAssistant('', '').answer('论文阅读的方法', [resource])
    assert answer['mode'] == 'retrieval'
    assert '尚未配置' in answer['answer']
    assert answer['sources'][0]['resourceId'] == 'resource'
    assert answer['sources'][0]['excerpt'] in resource.extracted_text
    assert OllamaResearchAssistant('', '').answer('unmatched', [resource])['sources'] == []
