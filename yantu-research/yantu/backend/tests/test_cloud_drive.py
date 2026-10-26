"""Real HTTP/database/filesystem acceptance for personal ownership and revocation."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4
import json
import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from yantu.app import create_app
from yantu.document_model import new_document, validate_document
from yantu.migrations import migrate
from yantu.models import Base


def data(response, status=200):
    assert response.status_code == status, response.text
    return response.json()['data']


@pytest.fixture
def drive(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLOW_PUBLIC_SIGNUP', '1')
    app = create_app(f'sqlite:///{tmp_path / "drive.db"}', tmp_path / 'uploads', tmp_path / 'front')
    with TestClient(app) as client:
        actors = []
        for index in range(4):
            email = f'drive{index}@example.com'
            uid = data(client.post('/api/v1/auth/register', json={'email': email, 'password': 'cloud-password-2026', 'displayName': f'成员{index}'}))['id']
            token = data(client.post('/api/v1/auth/login', json={'email': email, 'password': 'cloud-password-2026'}))['accessToken']
            actors.append((uid, {'Authorization': 'Bearer '+token}))
            client.cookies.clear()
        team = data(client.post('/api/v1/teams', headers=actors[0][1], json={'name': '云盘测试组'}))['id']
        for index in (1, 2):
            invitation = data(client.post(f'/api/v1/teams/{team}/invitations', headers=actors[0][1], json={'email': f'drive{index}@example.com', 'role': 'student'}))
            data(client.post(f'/api/v1/invitations/{invitation["inviteToken"]}/accept', headers=actors[index][1], json={}))
        yield client, actors, team, app


def upload(client, actor, folder='', key='file-1', content=b'Cloud research evidence', filename='研究笔记.txt'):
    return client.post('/api/v1/me/drive/files', headers={**actor, 'Idempotency-Key': key}, data={'folderId': folder, 'type': 'note'}, files={'file': (filename, content)})


def test_folders_files_isolation_and_idempotency(drive):
    c, actors, team, app = drive
    a, b, _, solo = [x[1] for x in actors]
    parent = None
    folders = []
    for title in ['课题 A', '参考论文', '方法']:
        parent = data(c.post('/api/v1/me/drive/folders', headers=a, json={'name': title, 'parentId': parent}), 201)['id']
        folders.append(parent)
    assert c.get('/api/v1/me/drive/children', headers=b, params={'folderId': parent}).status_code == 404
    assert c.patch('/api/v1/me/drive/folders/'+folders[0], headers=a, json={'parentId': parent}).status_code == 409
    assert c.delete('/api/v1/me/drive/folders/'+folders[0], headers=a).status_code == 409
    assert c.post('/api/v1/me/drive/folders', headers=a, json={'name': '方法', 'parentId': folders[1]}).status_code == 409
    assert c.post('/api/v1/me/drive/folders', headers=a, json={'name': '../invalid'}).status_code == 400
    file = data(upload(c, a, parent), 201)
    own_tree = data(c.get('/api/v1/me/drive/folders/tree', headers=a))
    assert own_tree['files'] == [{'id': file['id'], 'title': file['title'], 'folderId': parent, 'kind': 'file', 'ownerId': actors[0][0]}]
    assert data(c.get('/api/v1/me/drive/children', headers=a, params={'folderId': parent}))['items'][0]['createdAt']
    assert data(c.get('/api/v1/me/drive/folders/tree', headers=b))['files'] == []
    assert data(upload(c, a, parent), 201)['id'] == file['id']
    assert upload(c, a, parent, content=b'different').status_code == 409
    assert upload(c, b, parent).status_code == 404
    assert upload(c, a, key='empty', content=b'').status_code == 400
    assert upload(c, a, key='exe', filename='bad.exe').status_code == 415
    assert c.get('/api/v1/resources/'+file['id'], headers=b).status_code == 404
    assert c.get('/api/v1/resources/'+file['id']+'/download', headers=b).status_code == 404
    data(c.patch('/api/v1/resources/'+file['id'], headers=a, json={'title': '已重命名', 'folderId': folders[0]}))
    found = data(c.get('/api/v1/me/drive/search', headers=a, params={'scope': 'mine', 'q': '已重命名'}))['items']
    assert found[0]['id'] == file['id'] and found[0]['location'][-1]['id'] == folders[0]
    assert data(c.get('/api/v1/me/drive/children', headers=a, params={'folderId': parent}))['total'] == 0
    data(c.delete('/api/v1/me/drive/folders/'+parent, headers=a))
    # A user without any team can upload, preview, read and download.
    personal = data(upload(c, solo), 201)
    assert c.get('/api/v1/resources/'+personal['id']+'/download', headers=solo).content == b'Cloud research evidence'
    assert data(c.get('/api/v1/me/drive/children', headers=solo))['total'] == 1
    assert data(c.get('/api/v1/me/drive/children', headers=a))['total'] == 1
    keys = [(r.path, m) for r in app.routes for m in (getattr(r, 'methods', None) or [])]
    assert len(keys) == len(set(keys))
    assert '/api/v1/me/drive/files' in app.openapi()['paths']


def test_shares_versions_references_questions_and_departure(drive):
    c, actors, team, _ = drive
    aid, a = actors[0]; bid, b = actors[1]; cid, third = actors[2]
    file = data(upload(c, a), 201); rid = file['id']
    endpoint = '/api/v1/resources/'+rid
    data(c.put(endpoint+'/shares/'+bid, headers=a, json={'permission': 'read', 'teamId': team}))
    assert data(c.get('/api/v1/me/drive/search?scope=shared', headers=b))['items'][0]['id'] == rid
    shared_tree = data(c.get('/api/v1/me/drive/folders/tree', headers=b, params={'includeShared': 'true'}))
    assert shared_tree['files'][0]['id'] == rid and shared_tree['files'][0]['folderId'] is None
    shared_root = data(c.get('/api/v1/me/drive/children', headers=b, params={'includeShared': 'true'}))
    assert shared_root['items'][0]['id'] == rid and shared_root['items'][0]['ownerId'] == aid
    assert data(c.get('/api/v1/me/drive/children', headers=b))['items'] == []
    for suffix in ['', '/preview', '/download', '/versions', '/reading-progress']:
        assert c.get(endpoint+suffix, headers=third).status_code == 404
        assert c.get(endpoint+suffix, headers=b).status_code == 200
    assert c.patch(endpoint, headers=b, json={'title': 'stolen'}).status_code == 403
    data(c.patch(endpoint+'/reading-progress', headers=b, json={'page': 7, 'notes': '乙的笔记'}))
    assert data(c.get(endpoint+'/reading-progress', headers=a)) == {}
    data(c.post(endpoint+'/versions', headers=a, files={'file': ('新版本.txt', b'Cloud research updated evidence')}))
    versions = data(c.get(endpoint+'/versions', headers=b))['items']
    assert len(versions) == 2
    assert c.get(endpoint+'/download', headers=b).content == b'Cloud research updated evidence'
    assert c.get(endpoint+'/download', headers=b, params={'versionId': versions[0]['id']}).content == b'Cloud research evidence'
    task = data(c.post(f'/api/v1/teams/{team}/tasks', headers=a, json={'title': '科研任务', 'assigneeId': bid, 'reviewerId': aid}))['id']
    reference = data(c.post(f'/api/v1/tasks/{task}/resources', headers=a, json={'resourceId': rid}))
    assert data(c.post(f'/api/v1/tasks/{task}/resources', headers=a, json={'resourceId': rid}))['id'] == reference['id']
    assert data(c.get(f'/api/v1/tasks/{task}', headers=b))['resources'][0]['id'] == rid
    answer = data(c.post('/api/v1/me/drive/questions', headers=b, json={'question': 'Cloud research', 'resourceIds': [rid]}))
    assert answer['sources'][0]['resourceId'] == rid
    assert c.post('/api/v1/me/drive/questions', headers=third, json={'question': 'Cloud research', 'resourceIds': [rid]}).status_code == 404
    data(c.delete(endpoint+'/shares/'+bid, headers=a))
    assert data(c.get('/api/v1/me/drive/search?scope=shared', headers=b))['items'] == []
    assert data(c.get('/api/v1/me/drive/folders/tree', headers=b, params={'includeShared': 'true'}))['files'] == []
    assert data(c.get('/api/v1/me/drive/children', headers=b, params={'includeShared': 'true'}))['items'] == []
    assert data(c.get(f'/api/v1/tasks/{task}', headers=b))['resources'] == []
    assert c.get(endpoint+'/download', headers=b).status_code == 404
    assert c.post('/api/v1/me/drive/questions', headers=b, json={'question': 'Cloud research', 'resourceIds': [rid]}).status_code == 404
    # Shares issued in a team never revive after departure/rejoining.
    data(c.put(endpoint+'/shares/'+cid, headers=a, json={'permission': 'read', 'teamId': team}))
    data(c.delete(f'/api/v1/teams/{team}/members/{cid}', headers=a))
    invitation = data(c.post(f'/api/v1/teams/{team}/invitations', headers=a, json={'email': 'drive2@example.com', 'role': 'student'}))
    data(c.post('/api/v1/invitations/'+invitation['inviteToken']+'/accept', headers=third, json={}))
    assert c.get(endpoint, headers=third).status_code == 404
    # Legacy upload compatibility is private too, and search cannot bypass it.
    legacy = data(c.post(f'/api/v1/teams/{team}/resources', headers=a, data={'title': '私密兼容资料', 'type': 'note', 'visibility': 'team'}, files={'file': ('legacy.txt', b'legacy')}))
    assert c.get('/api/v1/resources/'+legacy['id'], headers=b).status_code == 404
    assert not data(c.get(f'/api/v1/teams/{team}/search?q=私密兼容资料', headers=b))['items']


def test_native_documents_and_text_workspace(drive):
    c, actors, team, _ = drive
    owner_id, owner = actors[0]
    reader_id, reader = actors[1]
    folder = data(c.post('/api/v1/me/drive/folders', headers=owner,
                         json={'name': '在线文档', 'parentId': None}), 201)['id']
    for kind, suffix, initial in [
        ('document', '.ytdoc', None),
        ('sheet', '.ytsheet', [['', '', ''] for _ in range(8)]),
        ('slides', '.ytslides', [{'title': '', 'body': ''}]),
    ]:
        created = data(c.post('/api/v1/me/drive/documents', headers=owner,
                              json={'kind': kind, 'title': '未命名', 'folderId': folder}), 201)
        assert created['fileName'].endswith(suffix)
        assert created['folderId'] == folder
        endpoint = '/api/v1/resources/'+created['id']+'/document'
        opened = data(c.get(endpoint, headers=owner))
        assert opened['kind'] == kind and opened['canEdit']
        if kind == 'document':
            assert opened['content']['schemaVersion'] == 2
            assert opened['content']['content'][0]['type'] == 'paragraph'
            UUID(opened['content']['content'][0]['attrs']['id'])
        else:
            assert opened['content'] == initial
        assert opened['modifiedAt']
        content = ({'schemaVersion': 2, 'type': 'doc', 'content': [
            {'type': 'heading', 'attrs': {'level': 1, 'id': str(uuid4())}, 'content': [{'type': 'text', 'text': '研究问题'}]},
            {'type': 'paragraph', 'attrs': {'id': str(uuid4())}, 'content': [{'type': 'text', 'text': '这是正文', 'marks': [{'type': 'link', 'attrs': {'href': 'https://example.com', 'target': '_blank', 'rel': 'noopener noreferrer nofollow', 'class': None, 'title': None}}]}]},
            {'type': 'blockMath', 'attrs': {'latex': r'\\frac{a}{b}', 'id': str(uuid4())}}]} if kind == 'document' else
                   [['数据', '42']] if kind == 'sheet' else [{'title': '第一页', 'body': '结论'}])
        saved = data(c.put(endpoint, headers=owner, json={'version': 1, 'content': content}))
        assert saved['version'] == 2 and saved['modifiedAt']
        assert c.put(endpoint, headers=owner, json={'version': True, 'content': content}).status_code == 400
        assert c.put(endpoint, headers=owner, json={'version': 2.0, 'content': content}).status_code == 400
        reopened = data(c.get(endpoint, headers=owner))
        assert reopened['content'] == content and reopened['modifiedAt'] == saved['modifiedAt']
        renamed = data(c.patch('/api/v1/resources/'+created['id'], headers=owner,
                               json={'title': '验收'+kind}))
        assert renamed['fileName'] == '验收'+kind+suffix
        assert c.put(endpoint, headers=owner, json={'version': 1, 'content': content}).status_code == 409
        assert len(data(c.get('/api/v1/resources/'+created['id']+'/versions', headers=owner))['items']) == 2
        assert c.get(endpoint, headers=reader).status_code == 404
        data(c.put('/api/v1/resources/'+created['id']+'/shares/'+reader_id, headers=owner,
                   json={'permission': 'read', 'teamId': team}))
        assert data(c.get(endpoint, headers=reader))['canEdit'] is False
        assert c.put(endpoint, headers=reader, json={'version': 2, 'content': content}).status_code == 403
        if kind == 'document':
            assert c.put(endpoint, headers=owner, json={'version': 2, 'content': '# 不再保存整段 Markdown'}).status_code == 400
            assert c.put(endpoint, headers=owner, json={'version': 2, 'content': {
                'schemaVersion': 2, 'type': 'doc', 'content': [{'type': 'script', 'text': 'bad'}]
            }}).status_code == 400
            assert c.put(endpoint, headers=owner, json={'version': 2, 'content': {
                'schemaVersion': 1, 'type': 'doc', 'content': [{'type': 'paragraph'}]
            }}).status_code == 400
    text_file = data(upload(c, owner, key='workspace-txt', content='初始正文'.encode('utf-8')),
                     201)
    text_endpoint = '/api/v1/resources/'+text_file['id']+'/document'
    assert data(c.get(text_endpoint, headers=owner))['content'] == '初始正文'
    assert data(c.put(text_endpoint, headers=owner,
                      json={'version': 1, 'content': '修改后的正文'}))['version'] == 2
    assert c.get('/api/v1/resources/'+text_file['id']+'/download', headers=owner).content == '修改后的正文'.encode('utf-8')
    assert c.put(text_endpoint, headers=owner, json={'version': 2, 'content': 42}).status_code == 400
    assert c.post('/api/v1/me/drive/documents', headers=owner,
                  json={'kind': 'unknown', 'title': '无效'}).status_code == 400


def test_document_image_and_attachment_references(drive):
    c, actors, team, _ = drive
    owner_id, owner = actors[0]
    reader_id, reader = actors[1]
    outsider = actors[3][1]
    doc = data(c.post('/api/v1/me/drive/documents', headers=owner,
                      json={'kind': 'document', 'title': '图文验收'}), 201)
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=')
    picture = data(upload(c, owner, key='embedded-image', content=png, filename='实验图.png'), 201)
    attachment = data(upload(c, owner, key='embedded-file', content=b'%PDF-1.4\nexample', filename='数据.pdf'), 201)
    alien = data(upload(c, outsider, key='alien-file', filename='别人的.txt'), 201)
    endpoint = f'/api/v1/resources/{doc["id"]}'
    image_node = {'type': 'imageResource', 'attrs': {'id': str(uuid4()), 'resourceId': picture['id'], 'name': picture['fileName']}}
    file_node = {'type': 'fileResource', 'attrs': {'id': str(uuid4()), 'resourceId': attachment['id'], 'name': attachment['fileName']}}
    content = {'schemaVersion': 2, 'type': 'doc', 'content': [image_node, file_node]}
    assert c.get(endpoint+'/assets/'+picture['id']+'/preview', headers=reader).status_code == 404


    assert data(c.put(endpoint+'/document', headers=owner, json={'version': 1, 'content': content}))['version'] == 2
    assert data(c.get(endpoint+'/document', headers=owner))['content'] == content
    assert c.get(endpoint+'/assets/'+picture['id']+'/preview', headers=owner).content == png
    assert c.get(endpoint+'/assets/'+attachment['id']+'/download', headers=owner).content == b'%PDF-1.4\nexample'
    data(c.put(endpoint+'/shares/'+reader_id, headers=owner, json={'permission': 'read', 'teamId': team}))
    assert c.get(endpoint+'/assets/'+picture['id']+'/preview', headers=reader).headers['content-type'] == 'image/png'
    assert c.get(endpoint+'/assets/'+picture['id']+'/download', headers=reader).content == png
    assert c.get(endpoint+'/assets/'+attachment['id']+'/download', headers=reader).status_code == 200
    assert c.get(endpoint+'/assets/'+alien['id']+'/download', headers=reader).status_code == 404
    assert c.get(endpoint+'/assets/'+attachment['id']+'/preview', headers=reader).status_code == 404
    bad = {'schemaVersion': 2, 'type': 'doc', 'content': [
        {'type': 'fileResource', 'attrs': {'id': str(uuid4()), 'resourceId': alien['id'], 'name': '别人的.txt'}}]}
    assert c.put(endpoint+'/document', headers=owner, json={'version': 2, 'content': bad}).status_code == 404
    assert c.put(endpoint+'/document', headers=owner, json={'version': 2, 'content': {
        'schemaVersion': 2, 'type': 'doc', 'content': [
            {'type': 'imageResource', 'attrs': {'id': str(uuid4()), 'resourceId': attachment['id'], 'name': '数据.pdf'}}]
    }}).status_code == 415
    assert c.put(endpoint+'/document', headers=owner, json={'version': 2, 'content': {
        'schemaVersion': 2, 'type': 'doc', 'content': [
            {'type': 'fileResource', 'attrs': {'id': str(uuid4()), 'resourceId': '../other', 'name': '错误引用'}}]
    }}).status_code == 400
    only_picture = {'schemaVersion': 2, 'type': 'doc', 'content': [image_node]}
    assert data(c.put(endpoint+'/document', headers=owner, json={'version': 2, 'content': only_picture}))['version'] == 3
    assert c.get(endpoint+'/assets/'+attachment['id']+'/download', headers=reader).status_code == 404
    assert c.get('/api/v1/resources/'+attachment['id']+'/download', headers=owner).status_code == 200
    data(c.delete(endpoint+'/shares/'+reader_id, headers=owner))
    assert c.get(endpoint+'/assets/'+picture['id']+'/preview', headers=reader).status_code == 404


def test_document_reference_has_identity_without_granting_target_access(drive):
    c, actors, team, _ = drive
    aid, author = actors[0]
    _, target_owner = actors[1]
    cid, reader = actors[2]
    source = data(c.post('/api/v1/me/drive/documents', headers=author,
                         json={'kind': 'document', 'title': '引用来源'}), 201)
    target = data(c.post('/api/v1/me/drive/documents', headers=target_owner,
                         json={'kind': 'document', 'title': '被引用的研究记录'}), 201)
    other = data(upload(c, author, key='not-native-document'), 201)
    endpoint = f'/api/v1/resources/{source["id"]}/document'
    paragraph = lambda reference: {'schemaVersion': 2, 'type': 'doc', 'content': [
        {'type': 'paragraph', 'attrs': {'id': str(uuid4())}, 'content': [
            {'type': 'text', 'text': '参见 '},
            {'type': 'documentReference', 'attrs': {'resourceId': reference}},
            {'type': 'text', 'text': ' 的结果。'},
        ]},
    ]}
    assert c.put(endpoint, headers=author, json={'version': 1, 'content': paragraph(target['id'])}).status_code == 404
    data(c.put(f'/api/v1/resources/{target["id"]}/shares/{aid}', headers=target_owner,
               json={'permission': 'read', 'teamId': team}))
    assert c.put(endpoint, headers=author, json={'version': 1, 'content': paragraph(other['id'])}).status_code == 400
    assert c.put(endpoint, headers=author, json={'version': 1, 'content': paragraph(source['id'])}).status_code == 400
    assert c.put(endpoint, headers=author, json={'version': 1, 'content': paragraph('../bad')}).status_code == 400
    content = paragraph(target['id'])
    assert data(c.put(endpoint, headers=author, json={'version': 1, 'content': content}))['version'] == 2
    assert data(c.get(endpoint, headers=author))['content'] == content
    data(c.put(f'/api/v1/resources/{source["id"]}/shares/{cid}', headers=author,
               json={'permission': 'read', 'teamId': team}))
    assert data(c.get(endpoint, headers=reader))['content'] == content
    assert c.get(f'/api/v1/resources/{target["id"]}', headers=reader).status_code == 404
    data(c.delete(f'/api/v1/resources/{target["id"]}/shares/{aid}', headers=target_owner))
    edited = paragraph(target['id'])
    edited['content'][0]['content'][0]['text'] = '撤销授权后仍能编辑原文：'
    assert data(c.put(endpoint, headers=author, json={'version': 2, 'content': edited}))['version'] == 3
    assert data(c.get(endpoint, headers=author))['content'] == edited
    assert c.get(f'/api/v1/resources/{target["id"]}', headers=author).status_code == 404


def test_simultaneous_document_saves_keep_one_version(drive):
    c, actors, _, _ = drive
    owner = actors[0][1]
    created = data(c.post('/api/v1/me/drive/documents', headers=owner,
                          json={'kind': 'document', 'title': '并发验收'}), 201)
    endpoint = '/api/v1/resources/'+created['id']+'/document'
    gate = Barrier(2)

    def save(content):
        gate.wait(timeout=10)
        structured = {'schemaVersion': 2, 'type': 'doc', 'content': [
            {'type': 'paragraph', 'attrs': {'id': str(uuid4())}, 'content': [{'type': 'text', 'text': content}]}
        ]}
        return c.put(endpoint, headers=owner, json={'version': 1, 'content': structured})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(save, '来自标签页 A')
        second = pool.submit(save, '来自标签页 B')
        responses = [first.result(timeout=30), second.result(timeout=30)]

    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = '来自标签页 A' if responses[0].status_code == 200 else '来自标签页 B'
    current = data(c.get(endpoint, headers=owner))
    assert current['content']['content'][0]['content'][0]['text'] == winner and current['version'] == 2
    assert len(data(c.get('/api/v1/resources/'+created['id']+'/versions', headers=owner))['items']) == 2


def test_document_model_v2_tables_ids_links_and_v1_read_compatibility(drive):
    c, actors, _, _ = drive
    owner = actors[0][1]
    legacy_bytes = json.dumps({'kind': 'document', 'content': {
        'schemaVersion': 1, 'type': 'doc', 'content': [
            {'type': 'heading', 'attrs': {'level': 2}, 'content': [{'type': 'text', 'text': '旧版标题'}]},
        ],
    }}, ensure_ascii=False).encode('utf-8')
    old = data(upload(c, owner, key='legacy-document-v1', content=legacy_bytes, filename='旧版.ytdoc'), 201)
    endpoint = '/api/v1/resources/'+old['id']+'/document'
    legacy_read = data(c.get(endpoint, headers=owner))
    assert legacy_read['content']['schemaVersion'] == 1 and legacy_read['canEdit']
    assert not legacy_read['compatibilityIssue']
    assert c.put(endpoint, headers=owner, json={'version': 1, 'content': {'schemaVersion': 1, 'type': 'doc', 'content': [{'type': 'paragraph'}]}}).status_code == 400

    identifier = lambda: str(uuid4())
    paragraph = lambda text_value: {'type': 'paragraph', 'attrs': {'id': identifier()},
                                    'content': [{'type': 'text', 'text': text_value}]}
    table = {'type': 'table', 'attrs': {'id': identifier()}, 'content': [
        {'type': 'tableRow', 'attrs': {'id': identifier()}, 'content': [
            {'type': 'tableHeader', 'attrs': {'id': identifier(), 'colspan': 1, 'rowspan': 1, 'colwidth': None, 'align': None, 'background': None}, 'content': [paragraph('项目')]},
            {'type': 'tableHeader', 'attrs': {'id': identifier(), 'colspan': 1, 'rowspan': 1, 'colwidth': None, 'align': None, 'background': None}, 'content': [paragraph('结果')]},
        ]},
        {'type': 'tableRow', 'attrs': {'id': identifier()}, 'content': [
            {'type': 'tableCell', 'attrs': {'id': identifier(), 'colspan': 1, 'rowspan': 1, 'colwidth': None, 'align': None, 'background': None}, 'content': [paragraph('实验 A')]},
            {'type': 'tableCell', 'attrs': {'id': identifier(), 'colspan': 1, 'rowspan': 1, 'colwidth': None, 'align': None, 'background': None}, 'content': [paragraph('通过')]},
        ]},
    ]}
    linked = paragraph('参考来源')
    linked['content'][0]['marks'] = [{'type': 'link', 'attrs': {'href': 'https://example.org/paper', 'target': '_blank', 'rel': 'noopener noreferrer nofollow', 'class': None, 'title': None}}]
    upgraded = {'schemaVersion': 2, 'type': 'doc', 'content': [linked, table]}
    assert data(c.put(endpoint, headers=owner, json={'version': 1, 'content': upgraded}))['version'] == 2
    assert data(c.get(endpoint, headers=owner))['content'] == upgraded
    assert '实验 A' in validate_document(upgraded)[1]

    duplicate = json.loads(json.dumps(upgraded, ensure_ascii=False))
    duplicate['content'][1]['attrs']['id'] = duplicate['content'][0]['attrs']['id']
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': duplicate}).status_code == 400
    unsafe = json.loads(json.dumps(upgraded, ensure_ascii=False))
    unsafe['content'][0]['content'][0]['marks'][0]['attrs']['href'] = 'javascript:alert(1)'
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': unsafe}).status_code == 400
    invalid_alignment = json.loads(json.dumps(upgraded, ensure_ascii=False))
    invalid_alignment['content'][1]['content'][0]['content'][0]['attrs']['align'] = 'expression(alert(1))'
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': invalid_alignment}).status_code == 400
    invalid_widths = json.loads(json.dumps(upgraded, ensure_ascii=False))
    invalid_widths['content'][1]['content'][0]['content'][0]['attrs']['colwidth'] = [120, 160]
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': invalid_widths}).status_code == 400
    missing_cell = json.loads(json.dumps(upgraded, ensure_ascii=False))
    missing_cell['content'][1]['content'][1]['content'].pop()
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': missing_cell}).status_code == 400
    old_irregular = data(upload(c, owner, key='legacy-irregular-table',
                                content=json.dumps({'kind': 'document', 'content': missing_cell}, ensure_ascii=False).encode('utf-8'),
                                filename='旧表格.ytdoc'), 201)
    irregular_read = data(c.get('/api/v1/resources/'+old_irregular['id']+'/document', headers=owner))
    assert irregular_read['content'] == missing_cell
    assert not irregular_read['canEdit'] and not irregular_read['canConvert']
    assert irregular_read['compatibilityIssue']
    merged_cell = json.loads(json.dumps(missing_cell, ensure_ascii=False))
    merged_cell['content'][1]['content'][0]['content'][0]['attrs']['rowspan'] = 2
    assert validate_document(merged_cell, for_write=True)[0] == merged_cell
    broken = json.loads(json.dumps(upgraded, ensure_ascii=False))
    broken['content'][1]['content'][0]['content'][0]['content'] = [{'type': 'text', 'text': '非法嵌套'}]
    assert c.put(endpoint, headers=owner, json={'version': 2, 'content': broken}).status_code == 400
    assert data(c.get(endpoint, headers=owner))['version'] == 2


def test_legacy_markdown_requires_review_before_structured_edit(drive, tmp_path):
    c, actors, _, _ = drive
    owner = actors[0][1]
    old = data(upload(c, owner, key='legacy-markdown', filename='旧文档.ytdoc',
                      content=json.dumps({'kind': 'document', 'content': '# 旧标题\n正文'}, ensure_ascii=False).encode('utf-8')), 201)
    endpoint = '/api/v1/resources/'+old['id']+'/document'
    preview = data(c.get(endpoint, headers=owner))
    assert preview['content'] == '# 旧标题\n正文'
    assert not preview['canEdit'] and preview['canConvert']
    assert preview['compatibilityIssue']

    converted = new_document()
    converted['content'][0]['content'] = [{'type': 'text', 'text': '正文'}]
    assert data(c.put(endpoint, headers=owner, json={'version': preview['version'], 'content': converted}))['version'] == 2
    reopened = data(c.get(endpoint, headers=owner))
    assert reopened['content'] == converted and reopened['canEdit']
    assert not reopened['canConvert'] and not reopened['compatibilityIssue']
    import sqlite3
    with sqlite3.connect(tmp_path / 'drive.db') as source:
        versions = source.execute('select version, storage_name from yt_resource_versions where resource_id=? order by version',
                                  (old['id'],)).fetchall()
    assert [version for version, _ in versions] == [1, 2]
    assert json.loads((tmp_path / 'uploads' / versions[0][1]).read_text(encoding='utf-8'))['content'] == '# 旧标题\n正文'


def test_document_title_rejects_stale_tab(drive):
    c, actors, _, _ = drive
    owner = actors[0][1]
    created = data(c.post('/api/v1/me/drive/documents', headers=owner,
                          json={'kind': 'document', 'title': '原标题'}), 201)
    assert created['isUntitled'] is False
    endpoint = '/api/v1/resources/'+created['id']
    renamed = data(c.patch(endpoint, headers=owner,
                           json={'title': '新的标题', 'expectedTitle': '原标题', 'expectedIsUntitled': False}))
    assert renamed['title'] == '新的标题' and renamed['fileName'] == '新的标题.ytdoc'
    assert c.patch(endpoint, headers=owner,
                   json={'title': '过期页面标题', 'expectedTitle': '原标题', 'expectedIsUntitled': False}).status_code == 409
    assert data(c.get(endpoint, headers=owner))['title'] == '新的标题'


def test_untitled_document_is_distinct_from_literal_title(drive):
    c, actors, _, _ = drive
    owner = actors[0][1]
    created = data(c.post('/api/v1/me/drive/documents', headers=owner, json={'kind': 'document'}), 201)
    assert created['title'] == '未命名文档' and created['isUntitled'] is True
    second = data(c.post('/api/v1/me/drive/documents', headers=owner, json={'kind': 'document'}), 201)
    assert second['title'] == '未命名文档 (2)' and second['isUntitled'] is True
    endpoint = '/api/v1/resources/'+created['id']
    assert data(c.get(endpoint+'/document', headers=owner))['isUntitled'] is True
    assert c.patch(endpoint, headers=owner, json={
        'title': '未命名文档', 'expectedTitle': '未命名文档',
    }).status_code == 400
    assert c.patch(endpoint, headers=owner, json={
        'title': '未命名文档', 'expectedTitle': '未命名文档', 'expectedIsUntitled': 'true',
    }).status_code == 400
    literal = data(c.patch(endpoint, headers=owner, json={
        'title': '未命名文档', 'expectedTitle': '未命名文档', 'expectedIsUntitled': True,
    }))
    assert literal['title'] == '未命名文档' and literal['isUntitled'] is False
    assert c.patch(endpoint, headers=owner, json={
        'title': '', 'expectedTitle': '未命名文档', 'expectedIsUntitled': True,
    }).status_code == 409
    cleared = data(c.patch(endpoint, headers=owner, json={
        'title': '', 'expectedTitle': '未命名文档', 'expectedIsUntitled': False,
    }))
    assert cleared['title'] == '未命名文档' and cleared['isUntitled'] is True
    assert data(c.get(endpoint, headers=owner))['isUntitled'] is True
    assert data(c.get(endpoint+'/document', headers=owner))['isUntitled'] is True


def test_legacy_sqlite_upgrade_is_repeatable_and_preserves_content(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO yt_users (id,email,password_hash,display_name,direction) VALUES ('u','u@x','hash','甲','')"))
        db.execute(text("INSERT INTO yt_teams (id,name) VALUES ('t','旧课题组')"))
        # Simulate the prior NOT NULL schema without changing any resource ID.
        db.exec_driver_sql('DROP TABLE yt_resources')
        db.exec_driver_sql('''CREATE TABLE yt_resources (id VARCHAR(36) PRIMARY KEY, team_id VARCHAR(36) NOT NULL REFERENCES yt_teams(id), owner_id VARCHAR(36) NOT NULL REFERENCES yt_users(id), title VARCHAR(200) NOT NULL, type VARCHAR(20) NOT NULL, description TEXT NOT NULL, extracted_text TEXT NOT NULL, meeting_id VARCHAR(36), task_id VARCHAR(36), file_name VARCHAR(255) NOT NULL, storage_name VARCHAR(36) UNIQUE NOT NULL, size INTEGER NOT NULL, visibility VARCHAR(20) NOT NULL DEFAULT 'team', archived BOOLEAN NOT NULL DEFAULT 'false', version INTEGER NOT NULL DEFAULT '1')''')
        db.exec_driver_sql("INSERT INTO yt_resources VALUES ('r','t','u','未命名文档','note','','旧文本',NULL,NULL,'未命名文档.ytdoc','original-storage',3,'team',0,1)")
        db.exec_driver_sql("INSERT INTO yt_resource_versions (id,resource_id,version,file_name,storage_name,size,note,author_id,created_at) VALUES ('v','r',1,'旧笔记.txt','original-storage',3,'','u',CURRENT_TIMESTAMP)")
        db.exec_driver_sql("INSERT INTO yt_entity_data (key,data) VALUES ('reading:r:u','{\"page\":7,\"notes\":\"saved\"}')")
    # Exercise an actual pre-upgrade snapshot and restore on a separate copy.
    import shutil
    import sqlite3
    source_files = tmp_path / 'files'
    source_files.mkdir()
    (source_files / 'original-storage').write_bytes(b'old')
    with sqlite3.connect(tmp_path / 'legacy.db') as source, sqlite3.connect(tmp_path / 'backup.db') as backup:
        source.backup(backup)
    shutil.copytree(source_files, tmp_path / 'backup-files')
    migrate(engine); migrate(engine)
    assert next(c for c in inspect(engine).get_columns('yt_resources') if c['name'] == 'team_id')['nullable']
    with engine.connect() as db:
        row = db.execute(text('SELECT id,owner_id,team_id,folder_id,storage_name,visibility,title,is_untitled FROM yt_resources')).one()
        assert tuple(row) == ('r', 'u', 't', None, 'original-storage', 'team', '未命名文档', False)
        assert db.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        assert db.execute(text('SELECT resource_id FROM yt_resource_versions')).scalar_one() == 'r'
    shutil.copy2(tmp_path / 'backup.db', tmp_path / 'restored.db')
    shutil.copytree(tmp_path / 'backup-files', tmp_path / 'restored-files')
    restored = create_engine(f'sqlite:///{tmp_path / "restored.db"}')
    migrate(restored)
    with restored.connect() as db:
        assert db.execute(text('SELECT storage_name FROM yt_resources WHERE id=\'r\'')).scalar_one() == 'original-storage'
        assert 'saved' in db.execute(text("SELECT data FROM yt_entity_data WHERE key='reading:r:u'")).scalar_one()
        assert db.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    assert (tmp_path / 'restored-files' / 'original-storage').read_bytes() == b'old'
    restored.dispose()
