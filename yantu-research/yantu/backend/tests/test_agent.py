"""Agent HTTP integration tests use isolated SQLite and fake upstream streams."""
import json
from pathlib import Path
import threading

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from yantu.app import create_app
from yantu.models import AgentAction, AgentConnection, Resource
from yantu.codex_bridge import CodexBridge


PASSWORD = 'research-agent-test-password'


@pytest.fixture
def agent_site(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLOW_PUBLIC_SIGNUP', '1')
    url = f'sqlite:///{tmp_path / "agent.db"}'
    app = create_app(url, tmp_path / 'uploads', tmp_path / 'frontend')
    with TestClient(app) as client:
        headers = []
        for name in ['alice', 'bob']:
            identity = {'email': name + '@example.com', 'password': PASSWORD, 'displayName': name}
            assert client.post('/api/v1/auth/register', json=identity).status_code == 200
            value = client.post('/api/v1/auth/login', json=identity).json()['data']
            headers.append({'Authorization': 'Bearer ' + value['accessToken']})
            client.cookies.clear()
        yield app, client, headers[0], headers[1], url, tmp_path


def data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()['data']


def save_connection(client, headers, provider='compatible', **extra):
    return data(client.post('/api/v1/agent/connections', headers=headers, json={
        'name': '测试连接', 'provider': provider, 'baseUrl': 'https://models.example.com/v1',
        'apiKey': 'private-api-key', 'models': ['test-model', 'second-model'], **extra,
    }))


def conversation(client, headers):
    return data(client.post('/api/v1/agent/conversations', headers=headers))['id']


def stream_events(response):
    assert response.status_code == 200, response.text
    events = []
    for part in response.text.split('\n\n'):
        if not part.startswith('event: '):
            continue
        lines = part.splitlines()
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    assert events[-1][0] == 'done', events
    return events


def sse(*events):
    return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                          content=''.join('data: ' + json.dumps(event) + '\n\n' for event in events) + 'data: [DONE]\n\n')


def test_credentials_are_encrypted_and_connections_are_private(agent_site):
    app, client, alice, bob, url, _ = agent_site
    saved = save_connection(client, alice)
    assert saved['hasKey'] is True
    assert 'private-api-key' not in json.dumps(saved)
    assert data(client.get('/api/v1/agent/connections', headers=bob))['items'] == []
    assert client.delete('/api/v1/agent/connections/' + saved['id'], headers=bob).status_code == 404
    with Session(create_engine(url)) as db:
        secret = db.get(AgentConnection, saved['id']).secret
        assert secret and 'private-api-key' not in secret
    seen = []
    def upstream(request):
        seen.append(request.headers['Authorization'])
        return httpx.Response(200, json={'data': [{'id': 'available-model'}]})
    app.state.agent_transport = httpx.MockTransport(upstream)
    updated = data(client.post('/api/v1/agent/connections/' + saved['id'] + '/models', headers=alice))
    assert updated['models'] == ['available-model']
    assert seen == ['Bearer private-api-key']
    save_connection(client, alice, id=saved['id'], apiKey='')
    with Session(create_engine(url)) as db:
        assert db.get(AgentConnection, saved['id']).secret == secret
    assert client.post('/api/v1/agent/connections', headers=alice, json={
        'name': 'bad', 'provider': 'compatible', 'baseUrl': 'http://169.254.169.254/latest', 'models': [],
    }).status_code == 400


def test_local_search_respects_file_and_conversation_permissions(agent_site):
    _, client, alice, bob, _, _ = agent_site
    uploaded = data(client.post('/api/v1/me/drive/files', headers=alice,
                    files={'file': ('experiment.txt', '实验使用固定随机种子。'.encode(), 'text/plain')},
                    data={'title': '实验设置'}), 201)
    ident = conversation(client, alice)
    assert client.get('/api/v1/agent/conversations/' + ident, headers=bob).status_code == 404
    assert client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=bob, json={'message': '查看实验设置'}).status_code == 404
    events = stream_events(client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=alice,
                                     json={'message': '实验随机种子', 'model': 'local-search', 'resourceIds': [uploaded['id']]}))
    assert any('固定随机种子' in event.get('text', '') for kind, event in events if kind == 'delta')
    stored = data(client.get('/api/v1/agent/conversations/' + ident, headers=alice))
    assert len(stored['messages']) == 2
    assert stored['messages'][-1]['details']['sources'][0]['resourceId'] == uploaded['id']
    other = conversation(client, bob)
    assert client.post(f'/api/v1/agent/conversations/{other}/messages', headers=bob,
                       json={'message': '查看资料', 'resourceIds': [uploaded['id']]}).status_code == 404


def test_tool_loop_drafts_require_approval_and_save_exactly_once(agent_site):
    app, client, alice, bob, url, folder = agent_site
    saved = save_connection(client, alice)
    calls = []
    def upstream(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return sse({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call-note', 'function': {
                'name': 'draft_note', 'arguments': json.dumps({'title': '实验计划', 'content': '# 计划\n先阅读资料。'})}}]}}]})
        assert body['messages'][-1]['role'] == 'tool'
        return sse({'choices': [{'delta': {'content': '笔记草稿已准备，请确认保存。'}}]})
    app.state.agent_transport = httpx.MockTransport(upstream)
    ident = conversation(client, alice)
    events = stream_events(client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=alice,
                           json={'message': '起草一份实验计划', 'connectionId': saved['id'], 'model': 'test-model', 'mode': 'agent'}))
    assert events[-1][1]['status'] == 'complete', events
    action = next(value for kind, value in events if kind == 'action')
    with Session(create_engine(url)) as db:
        assert not db.scalars(select(Resource)).all()
        assert db.get(AgentAction, action['id']).status == 'pending'
    endpoint = '/api/v1/agent/actions/' + action['id']
    assert client.post(endpoint, headers=bob, json={'approve': True}).status_code == 404
    approved = data(client.post(endpoint, headers=alice, json={'approve': True}))
    again = data(client.post(endpoint, headers=alice, json={'approve': True}))
    assert approved['resourceId'] == again['resourceId']
    with Session(create_engine(url)) as db:
        resources = db.scalars(select(Resource)).all()
        assert len(resources) == 1 and resources[0].visibility == 'private'
        assert (folder / 'uploads' / resources[0].storage_name).read_text() == '# 计划\n先阅读资料。'
    assert client.get('/api/v1/resources/' + approved['resourceId'], headers=bob).status_code == 404


@pytest.mark.parametrize('provider', ['openai', 'compatible', 'ollama'])
def test_streaming_and_multiturn_model_switch(provider, agent_site):
    app, client, alice, _, _, _ = agent_site
    saved = save_connection(client, alice, provider=provider)
    requests = []
    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        if provider == 'openai':
            assert request.url.path.endswith('/responses')
            return sse({'type': 'response.output_text.delta', 'delta': '你好'},
                       {'type': 'response.completed', 'response': {'output': [{'id': 'msg-1', 'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': '你好'}]}]}})
        if provider == 'ollama':
            return httpx.Response(200, content=json.dumps({'message': {'content': '你好'}, 'done': True}) + '\n')
        return sse({'choices': [{'delta': {'content': '你好'}}]})
    app.state.agent_transport = httpx.MockTransport(upstream)
    ident = conversation(client, alice)
    for model in ['test-model', 'second-model']:
        events = stream_events(client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=alice,
                               json={'message': '继续讨论', 'connectionId': saved['id'], 'model': model, 'mode': 'chat'}))
        assert events[-1][1]['status'] == 'complete', events
    assert requests[-1]['model'] == 'second-model'
    history = requests[-1].get('input') or requests[-1].get('messages')
    assert any(item.get('role') == 'assistant' and item.get('content') == '你好' for item in history)
    stored = data(client.get('/api/v1/agent/conversations/' + ident, headers=alice))
    assert len(stored['messages']) == 4
    assert stored['messages'][-1]['model'] == 'second-model'


def test_provider_errors_are_persisted_without_secrets(agent_site):
    app, client, alice, _, _, _ = agent_site
    saved = save_connection(client, alice)
    app.state.agent_transport = httpx.MockTransport(lambda request: httpx.Response(401, json={'error': 'private-api-key'}))
    ident = conversation(client, alice)
    events = stream_events(client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=alice,
                           json={'message': '你好', 'connectionId': saved['id'], 'model': 'test-model'}))
    assert events[-1][1]['status'] == 'error'
    assert 'private-api-key' not in json.dumps(events)
    stored = data(client.get('/api/v1/agent/conversations/' + ident, headers=alice))
    assert '认证失败' in stored['messages'][-1]['details']['error']


def test_stop_and_parallel_send_are_scoped_to_the_conversation_owner(agent_site):
    app, client, alice, bob, _, _ = agent_site
    saved = save_connection(client, alice)
    started, release = threading.Event(), threading.Event()

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"started"}}]}\n\n'
            started.set()
            assert release.wait(10)
            yield b'data: [DONE]\n\n'

    app.state.agent_transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))
    ident = conversation(client, alice)
    endpoint = f'/api/v1/agent/conversations/{ident}'
    result = []
    thread = threading.Thread(target=lambda: result.append(client.post(endpoint + '/messages', headers=alice,
                              json={'message': '长时间任务', 'connectionId': saved['id'], 'model': 'test-model'})))
    thread.start()
    try:
        assert started.wait(10)
        assert client.post(endpoint + '/messages', headers=alice, json={'message': '重复请求'}).status_code == 409
        assert client.post(endpoint + '/stop', headers=bob).status_code == 404
        assert client.post(endpoint + '/stop', headers=alice).status_code == 200
    finally:
        release.set()
        thread.join(10)
    assert stream_events(result[0])[-1][1]['status'] == 'stopped'
    assert data(client.get(endpoint, headers=alice))['messages'][-1]['content'] == 'started'


def test_responses_function_output_and_forbidden_file_are_handled(agent_site):
    app, client, alice, bob, _, _ = agent_site
    private = data(client.post('/api/v1/me/drive/files', headers=bob,
                   files={'file': ('secret.txt', b'private-research-secret', 'text/plain')}, data={'title': '秘密资料'}), 201)
    saved = save_connection(client, alice, provider='openai')
    count = 0
    def upstream(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        if count == 1:
            assert all(tool['strict'] for tool in body['tools'])
            return sse({'type': 'response.completed', 'response': {'output': [{
                'id': 'function-1', 'type': 'function_call', 'call_id': 'read-1', 'name': 'read_resource',
                'arguments': json.dumps({'resource_id': private['id']})}]}})
        output = body['input'][-1]
        assert output['type'] == 'function_call_output' and output['call_id'] == 'read-1'
        assert '无权访问' in json.loads(output['output'])['error']
        assert 'private-research-secret' not in json.dumps(body)
        return sse({'type': 'response.output_text.delta', 'delta': '无法访问这份资料。'},
                   {'type': 'response.completed', 'response': {'output': []}})
    app.state.agent_transport = httpx.MockTransport(upstream)
    ident = conversation(client, alice)
    events = stream_events(client.post(f'/api/v1/agent/conversations/{ident}/messages', headers=alice,
                           json={'message': '阅读这份资料', 'connectionId': saved['id'], 'model': 'test-model'}))
    assert events[-1][1]['status'] == 'complete', events
    assert any(value.get('status') == 'error' for kind, value in events if kind == 'tool')


def test_codex_stdio_handshake_login_and_research_tools(tmp_path, monkeypatch):
    fake = tmp_path / 'codex-test'
    fake.write_text('''#!/usr/local/bin/python
import json, os, sys
assert 'OPENAI_API_KEY' not in os.environ
assert os.environ['CODEX_HOME'].endswith('private-home')
for line in sys.stdin:
 m=json.loads(line); method=m.get('method'); ident=m.get('id'); p=m.get('params',{})
 if method=='initialized': continue
 if method=='initialize': result={}
 elif method=='account/read': result={'account':None}
 elif method=='account/login/start':
  assert p['type']=='chatgptDeviceCode'
  result={'loginId':'login-1','verificationUrl':'https://auth.openai.com/codex/device','userCode':'ABCD-1234'}
 elif method=='thread/start':
  assert p['config']['features.shell_tool'] is False
  assert p['sandbox']=='read-only'
  result={'thread':{'id':'thread-1'}}
 elif method=='turn/start':
  result={'turn':{'id':'turn-1'}}
 elif method=='thread/unsubscribe': result={}
 elif not method:
  assert m['result']['success'] is True
  print(json.dumps({'method':'item/agentMessage/delta','params':{'threadId':'thread-1','delta':'已检索资料。'}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':'thread-1','turn':{'id':'turn-1','status':'completed'}}}),flush=True)
  continue
 else: raise AssertionError(method)
 print(json.dumps({'id':ident,'result':result}),flush=True)
 if method=='turn/start':
  print(json.dumps({'method':'item/tool/call','id':999,'params':{'threadId':'thread-1','tool':'search_resources','arguments':{'query':'实验'}}}),flush=True)
''')
    fake.chmod(0o755)
    monkeypatch.setenv('OPENAI_API_KEY', 'host-secret-must-not-be-inherited')
    bridge = CodexBridge(tmp_path / 'private-home', str(fake))
    try:
        assert bridge.status()['connected'] is False
        assert bridge.start_login()['userCode'] == 'ABCD-1234'
        events, tools = [], []
        answer = bridge.run('model', [{'role': 'user', 'content': '读资料'}], 'system', [],
                            lambda name, args: tools.append((name, args)) or {'items': []},
                            lambda kind, value: events.append((kind, value)), threading.Event())
        assert answer == '已检索资料。'
        assert tools == [('search_resources', {'query': '实验'})]
    finally:
        bridge.close()
