"""Drive integration with the laboratory membership and material policies."""
import pytest

from test_lab import site, group, register, approve, meeting, data, upload as project_upload
from test_cloud_drive import test_folders_files_isolation_and_idempotency


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()['data']


def upload(client, actor, content=b'original data', key='cloud-file'):
    return ok(client.post('/api/v1/me/drive/files', headers={**actor, 'Idempotency-Key': key},
                         data={'type': 'note'}, files={'file': ('research.txt', content, 'text/plain')}), 201)


@pytest.fixture
def drive(site):
    persons = [register(site, f'drive{i}') for i in range(4)]
    project = ok(site.post('/api/v1/lab/projects', headers=persons[0]['auth'], json={'name': '云盘课题'}), 201)
    for person in persons[1:3]:
        approve(site, persons[0], project['id'], person)
    yield site, [(p['id'], p['auth']) for p in persons], project['id'], site.app


def test_shared_personal_files_versions_reading_history_and_revocation(group):
    c, owner, member, outsider = (group[k] for k in ('client', 'owner', 'member', 'outsider'))
    project_id = group['project']['id']
    file = upload(c, owner['auth'])
    endpoint = '/api/v1/resources/' + file['id']
    assert ok(c.get(endpoint, headers=owner['auth']))['canEdit'] is True
    for suffix in ('', '/download', '/preview', '/versions', '/reading-progress'):
        assert c.get(endpoint + suffix, headers=member['auth']).status_code == 404
        assert c.get(endpoint + suffix).status_code == 401
    ok(c.put(endpoint + '/shares/' + member['id'], headers=owner['auth'], json={'permission':'read','teamId':project_id}))
    assert ok(c.get('/api/v1/me/drive/shared', headers=member['auth']))['items'][0]['id'] == file['id']
    for suffix in ('', '/download', '/preview', '/versions', '/reading-progress'):
        assert c.get(endpoint + suffix, headers=member['auth']).status_code == 200
        assert c.get(endpoint + suffix, headers=outsider['auth']).status_code == 404
    assert c.patch(endpoint, headers=member['auth'], json={'title':'stolen'}).status_code == 403
    assert c.post(endpoint + '/versions', headers=member['auth'], files={'file':('new.txt', b'changed')}).status_code == 403
    assert c.get(endpoint + '/shares', headers=member['auth']).status_code == 403
    assert c.put(endpoint + '/shares/' + outsider['id'], headers=owner['auth'], json={'permission':'read','teamId':project_id}).status_code == 400
    ok(c.patch(endpoint + '/reading-progress', headers=member['auth'], json={'page':7,'notes':'我的笔记'}))
    assert ok(c.get(endpoint + '/reading-progress', headers=owner['auth'])) == {}
    ok(c.post('/api/v1/lab/history', headers=member['auth'], json={'targetType':'resource','targetId':file['id']}))
    ok(c.post(endpoint + '/versions', headers=owner['auth'], files={'file':('updated.txt', b'updated data')}, data={'note':'修订记录'}))
    versions = ok(c.get(endpoint + '/versions', headers=member['auth']))['items']
    assert [v['version'] for v in versions] == [1,2]
    first = c.get(endpoint + '/download', headers=member['auth'], params={'versionId':versions[0]['id']})
    assert first.content == b'original data'
    assert 'research.txt' in first.headers['content-disposition']
    assert c.get(endpoint + '/download', headers=member['auth']).content == b'updated data'
    ok(c.delete(endpoint + '/shares/' + member['id'], headers=owner['auth']))
    for suffix in ('', '/download', '/preview', '/versions', '/reading-progress'):
        assert c.get(endpoint + suffix, headers=member['auth']).status_code == 404
    assert ok(c.get('/api/v1/me/drive/shared', headers=member['auth']))['items'] == []
    assert ok(c.get('/api/v1/lab/history', headers=member['auth']))['items'] == []


def test_cloud_references_reuse_file_require_explicit_grant_and_follow_versions(group):
    c, owner, member, outsider = (group[k] for k in ('client', 'owner', 'member', 'outsider'))
    project_id = group['project']['id']
    scheduled = meeting(c, owner, project_id)
    file = upload(c, member['auth'])
    endpoint = f'/api/v1/lab/projects/{project_id}/materials/references'
    payload = {'resourceId':file['id']}
    assert c.post(endpoint, headers=member['auth'], json=payload).status_code == 400
    assert c.get('/api/v1/resources/' + file['id'], headers=owner['auth']).status_code == 404
    payload['grantReadAccess'] = True
    reference = ok(c.post(endpoint, headers=member['auth'], json=payload), 201)
    assert reference['id'] == file['id']
    duplicate = ok(c.post(endpoint, headers=member['auth'], json=payload), 201)
    assert duplicate['referenceId'] == reference['referenceId']
    assert len(ok(c.get(f'/api/v1/lab/projects/{project_id}/materials', headers=owner['auth']))['items']) == 1
    meeting_ref = ok(c.post(endpoint, headers=member['auth'], json={**payload,'meetingId':scheduled['id']}), 201)
    detail = ok(c.get('/api/v1/lab/meetings/' + scheduled['id'], headers=owner['auth']))
    assert [x['id'] for x in detail['materials']] == [file['id']]
    assert c.post(endpoint, headers=owner['auth'], json=payload).status_code == 403
    assert c.post(endpoint, headers=outsider['auth'], json=payload).status_code in (403,404)
    resource_path = '/api/v1/resources/' + file['id']
    ok(c.post(resource_path + '/versions', headers=member['auth'], files={'file':('v2.txt',b'new version')}))
    detail = ok(c.get('/api/v1/lab/meetings/' + scheduled['id'], headers=owner['auth']))
    assert detail['materials'][0]['version'] == 2
    assert c.get(resource_path + '/download', headers=owner['auth']).content == b'new version'
    ok(c.delete(resource_path + '/shares/' + owner['id'], headers=member['auth']))
    assert ok(c.get(f'/api/v1/lab/projects/{project_id}/materials', headers=owner['auth']))['items'] == []
    assert ok(c.get('/api/v1/lab/meetings/' + scheduled['id'], headers=owner['auth']))['materials'] == []
    assert c.get(resource_path + '/download', headers=owner['auth']).status_code == 404


def test_project_uploads_never_appear_in_personal_drive_or_bypass_departure(group):
    c, owner, member = (group[k] for k in ('client','owner','member'))
    project_id = group['project']['id']
    course_file, _ = project_upload(c, member, project_id)
    private_file = upload(c, member['auth'])
    own = ok(c.get('/api/v1/me/drive/children', headers=member['auth']))
    assert [x['id'] for x in own['items']] == [private_file['id']]
    tree = ok(c.get('/api/v1/me/drive/folders/tree', headers=member['auth'], params={'includeShared':True}))
    assert [x['id'] for x in tree['files']] == [private_file['id']]
    assert c.put('/api/v1/resources/' + course_file['id'] + '/shares/' + owner['id'], headers=member['auth'], json={'permission':'read','teamId':project_id}).status_code == 400
    reference_path = f'/api/v1/lab/projects/{project_id}/materials/references'
    ok(c.post(reference_path, headers=member['auth'], json={'resourceId':private_file['id'],'grantReadAccess':True}), 201)
    ok(c.delete(f'/api/v1/teams/{project_id}/members/{member["id"]}', headers=owner['auth']))
    for suffix in ('', '/download','/preview','/versions'):
        assert c.get('/api/v1/resources/' + course_file['id'] + suffix, headers=member['auth']).status_code in (403,404)
    assert c.get('/api/v1/resources/' + private_file['id'] + '/download', headers=member['auth']).status_code == 200
    assert c.get('/api/v1/resources/' + private_file['id'] + '/download', headers=owner['auth']).status_code == 404
    approve(c, owner, project_id, member)
    assert c.get('/api/v1/resources/' + private_file['id'] + '/download', headers=owner['auth']).status_code == 404


def test_drive_does_not_restore_assistant_or_task_feedback_routes(group):
    c, owner = group['client'], group['owner']
    for path in ('/api/v1/me/drive/questions','/api/v1/tasks/task/submissions','/api/v1/submissions/submission/reviews','/api/v1/tasks/task/resources'):
        assert c.post(path, headers=owner['auth'], json={}).status_code in (404,405)
