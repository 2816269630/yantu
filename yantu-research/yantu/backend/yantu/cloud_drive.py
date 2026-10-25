"""Personal drive access policy shared by every legacy and new resource endpoint."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (DriveFolder, Member, Resource, ResourceReference, ResourceShare,
                     ResourceVersion, UploadReceipt, User, Task, Meeting, utcnow)
from .research_assistant import AssistantUnavailable, extract_document_text
from .document_model import new_document, validate_document

EXTENSIONS = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.zip', '.ytdoc', '.ytsheet', '.ytslides']
NATIVE_FORMATS = {'document': ('.ytdoc', 'note'), 'sheet': ('.ytsheet', 'other'), 'slides': ('.ytslides', 'slides')}


def member_of(db, team_id, user_id):
    return db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id)) if team_id else None


def valid_share(db, share, resource):
    return share.active and member_of(db, share.team_id, share.user_id) and member_of(db, share.team_id, resource.owner_id)


def resource_visible(db, resource, user, membership=None):
    if resource.archived:
        return False
    if resource.owner_id == user.id:
        return True
    if resource.visibility == 'team' and member_of(db, resource.team_id, user.id):
        return True  # Preserve the original team audience, never expand it to all accounts.
    return any(valid_share(db, s, resource) for s in db.scalars(select(ResourceShare).where(
        ResourceShare.resource_id == resource.id, ResourceShare.user_id == user.id, ResourceShare.active.is_(True))))


def resource_for(db, resource_id, user, write=False):
    resource = db.get(Resource, resource_id)
    if not resource or not resource_visible(db, resource, user):
        raise HTTPException(404, '资料不存在或无权访问')
    if write and resource.owner_id != user.id:
        raise HTTPException(403, '只有文件所有者可以修改')
    return resource, member_of(db, resource.team_id, user.id)


def register_cloud_drive(app, ctx):
    get_db, current_user = ctx['get_db'], ctx['current_user']
    resource_json, iso = ctx['resource_json'], ctx['iso']
    uploads, assistant = ctx['uploads'], ctx['assistant']

    def result(data):
        return {'data': data}

    def name(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200 or any(c in value for c in '/\\:*?"<>|') or any(ord(c) < 32 for c in value) or value.strip() in ('.', '..'):
            raise HTTPException(400, '名称不能为空，最多 200 字，不能包含路径符号或控制字符')
        return value.strip()

    def folder_for(db, folder_id, user):
        if not folder_id:
            return None
        row = db.get(DriveFolder, folder_id)
        if not row or row.owner_id != user.id:
            raise HTTPException(404, '目录不存在或无权访问')
        return row

    def folder_json(row):
        return {'id': row.id, 'name': row.name, 'parentId': row.parent_id, 'ownerId': row.owner_id, 'createdAt': iso(row.created_at)}

    def breadcrumbs(db, folder_id, user):
        items, seen = [], set()
        while folder_id:
            if folder_id in seen:
                raise HTTPException(409, '目录层级异常')
            seen.add(folder_id)
            row = folder_for(db, folder_id, user)
            items.insert(0, folder_json(row))
            folder_id = row.parent_id
        return [{'id': None, 'name': '我的文件'}] + items

    def file_json(db, row, user):
        item = resource_json(db, row, user)
        item['createdAt'] = iso(db.scalar(select(ResourceVersion.created_at).where(
            ResourceVersion.resource_id == row.id
        ).order_by(ResourceVersion.version).limit(1)))
        item['folderId'] = row.folder_id
        item['location'] = breadcrumbs(db, row.folder_id, user) if row.owner_id == user.id else []
        item['permissions'] = {'canRead': True, 'canDownload': True, 'canEdit': row.owner_id == user.id, 'canShare': row.owner_id == user.id, 'canMove': row.owner_id == user.id}
        item['accessSources'] = (['owner'] if row.owner_id == user.id else []) + (['legacyTeam'] if row.visibility == 'team' and member_of(db, row.team_id, user.id) else [])
        if any(valid_share(db, s, row) for s in db.scalars(select(ResourceShare).where(ResourceShare.resource_id == row.id, ResourceShare.user_id == user.id))):
            item['accessSources'].append('direct')
        return item

    def paginate(items, page, page_size):
        return result({'items': items[(page-1)*page_size:page*page_size], 'total': len(items), 'page': page, 'pageSize': page_size})

    def check_duplicate(db, user, parent, title, exclude=None):
        if db.scalar(select(DriveFolder.id).where(DriveFolder.owner_id == user.id, DriveFolder.parent_id == parent, DriveFolder.name == title, DriveFolder.id != (exclude or ''))):
            raise HTTPException(409, '该目录下已存在同名文件夹')

    @app.get('/api/v1/me/drive/config')
    def config(user: User = Depends(current_user)):
        return result({'maxUploadBytes': int(os.getenv('MAX_UPLOAD_BYTES', 20*1024*1024)), 'allowedExtensions': EXTENSIONS, 'extractableExtensions': ['.pdf', '.docx', '.txt', '.md'], 'maxQuestionResources': 100, 'maxQuestionLength': 500})

    @app.get('/api/v1/me/drive/folders/tree')
    def tree(includeShared: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
        rows = db.scalars(select(DriveFolder).where(DriveFolder.owner_id == user.id).order_by(DriveFolder.name)).all()
        files = db.execute(select(Resource.id, Resource.title, Resource.folder_id).where(
            Resource.owner_id == user.id, Resource.archived.is_(False)
        ).order_by(Resource.title, Resource.id)).all()
        own_files = [
            {'id': ident, 'title': title, 'folderId': folder_id, 'kind': 'file', 'ownerId': user.id}
            for ident, title, folder_id in files
        ]
        shared_files = [
            {'id': row.id, 'title': row.title, 'folderId': None, 'kind': 'file', 'ownerId': row.owner_id}
            for row in available_rows(db, user, 'shared', '')
        ] if includeShared else []
        return result({'items': [folder_json(r) for r in rows], 'files': own_files + shared_files})

    @app.get('/api/v1/me/drive/children')
    def children(folderId: str = '', includeShared: bool = False, page: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        folder_for(db, folderId, user)
        folders = db.scalars(select(DriveFolder).where(DriveFolder.owner_id == user.id, DriveFolder.parent_id == (folderId or None)).order_by(DriveFolder.name)).all()
        files = db.scalars(select(Resource).where(Resource.owner_id == user.id, Resource.folder_id == (folderId or None), Resource.archived.is_(False)).order_by(Resource.title)).all()
        items = [{**folder_json(r), 'kind': 'folder'} for r in folders] + [{**file_json(db, r, user), 'kind': 'file'} for r in files]
        if includeShared and not folderId:
            items += [{**file_json(db, r, user), 'folderId': None, 'kind': 'file'} for r in available_rows(db, user, 'shared', '')]
        return result({'items': items[(page-1)*pageSize:page*pageSize], 'total': len(items), 'page': page, 'pageSize': pageSize, 'breadcrumbs': breadcrumbs(db, folderId, user)})

    @app.post('/api/v1/me/drive/folders', status_code=201)
    def create_folder(payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        parent = payload.get('parentId') or None
        folder_for(db, parent, user)
        title = name(payload.get('name'))
        check_duplicate(db, user, parent, title)
        row = DriveFolder(owner_id=user.id, parent_id=parent, name=title)
        db.add(row); db.commit()
        return result(folder_json(row))

    @app.patch('/api/v1/me/drive/folders/{folder_id}')
    def edit_folder(folder_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = folder_for(db, folder_id, user)
        parent = payload.get('parentId', row.parent_id) or None
        folder_for(db, parent, user)
        if any(x['id'] == row.id for x in breadcrumbs(db, parent, user)):
            raise HTTPException(409, '不能移动到自身或子目录')
        title = name(payload.get('name', row.name))
        check_duplicate(db, user, parent, title, row.id)
        row.name, row.parent_id = title, parent
        db.commit()
        return result(folder_json(row))

    @app.delete('/api/v1/me/drive/folders/{folder_id}')
    def delete_folder(folder_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = folder_for(db, folder_id, user)
        if db.scalar(select(DriveFolder.id).where(DriveFolder.parent_id == row.id)) or db.scalar(select(Resource.id).where(Resource.folder_id == row.id)):
            raise HTTPException(409, '只能删除空文件夹，请先移走文件和子目录')
        db.delete(row); db.commit()
        return result(None)

    def available_rows(db, user, scope, q):
        if scope not in ('mine', 'shared', 'all'):
            raise HTTPException(400, '搜索范围无效')
        query = select(Resource).where(Resource.archived.is_(False)).order_by(Resource.title, Resource.id)
        if scope == 'mine':
            query = query.where(Resource.owner_id == user.id)
        elif scope == 'shared':
            query = query.where(Resource.owner_id != user.id)
        return [r for r in db.scalars(query) if resource_visible(db, r, user) and q.casefold() in r.title.casefold()]

    def target_for(db, kind, ident, user):
        if kind == 'task':
            row, _, _ = ctx['task_for'](db, ident, user)
            users = [row.assignee_id, row.reviewer_id]
        elif kind == 'meeting':
            row = db.get(Meeting, ident)
            if not row: raise HTTPException(404, '组会不存在')
            ctx['team_member'](db, row.team_id, user)
            users = list(db.scalars(select(Member.user_id).where(Member.team_id == row.team_id)))
        else:
            raise HTTPException(400, '引用类型无效')
        return row, list(dict.fromkeys(users))

    @app.get('/api/v1/me/drive/search')
    @app.get('/api/v1/me/drive/shared')
    @app.get('/api/v1/me/drive/available-resources')
    def available(request: Request, scope: str = 'all', q: str = '', page: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=100), targetType: str = '', targetId: str = '', user: User = Depends(current_user), db: Session = Depends(get_db)):
        if request.url.path.endswith('/shared'): scope = 'shared'
        audience = target_for(db, targetType, targetId, user)[1] if targetType else []
        rows = available_rows(db, user, scope, q)
        items = [file_json(db, r, user) for r in rows]
        if audience:
            for item, row in zip(items, rows):
                item['audience'] = [{'userId': uid, 'displayName': ctx['name'](db, uid), 'canRead': resource_visible(db, row, db.get(User, uid))} for uid in audience]
        return paginate(items, page, pageSize)

    @app.patch('/api/v1/resources/{resource_id}')
    def edit_file(resource_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        if 'visibility' in payload and payload['visibility'] != row.visibility:
            raise HTTPException(400, '请通过指定成员共享管理授权，不能扩大旧课题组可见范围')
        if 'expectedTitle' in payload:
            if set(payload) != {'title', 'expectedTitle'} or not isinstance(payload['expectedTitle'], str):
                raise HTTPException(400, '标题更新参数无效')
            title = name(payload['title'])
            extension = Path(row.file_name).suffix.lower()
            values = {'title': title}
            if extension in {suffix for suffix, _ in NATIVE_FORMATS.values()}:
                values['file_name'] = title[:255-len(extension)] + extension
            changed = db.execute(update(Resource).where(
                Resource.id == row.id, Resource.owner_id == user.id,
                Resource.title == payload['expectedTitle'], Resource.archived.is_(False)
            ).values(**values).execution_options(synchronize_session=False)).rowcount
            if changed != 1:
                db.rollback()
                raise HTTPException(409, '标题已在其他页面修改，请保留当前输入并重新加载')
            db.commit()
            db.refresh(row)
            return result(file_json(db, row, user))
        if 'title' in payload:
            row.title = name(payload['title'])
            extension = Path(row.file_name).suffix.lower()
            if extension in {suffix for suffix, _ in NATIVE_FORMATS.values()}:
                row.file_name = row.title[:255-len(extension)] + extension
        if 'description' in payload: row.description = ctx['text_value'](payload, 'description')
        if 'folderId' in payload:
            folder_for(db, payload['folderId'], user)
            row.folder_id = payload['folderId'] or None
        if 'tags' in payload: ctx['put_meta'](db, 'resource', row.id, {'tags': ctx['tags'](payload)})
        db.commit()
        return result(file_json(db, row, user))

    def validate_file(filename, content):
        filename = (filename or '').replace('\\', '/').split('/')[-1].replace('\r', '').replace('\n', '')[:255]
        if not content: raise HTTPException(400, '不能上传空文件')
        if len(content) > int(os.getenv('MAX_UPLOAD_BYTES', 20*1024*1024)): raise HTTPException(413, '文件超过上传大小限制')
        if Path(filename).suffix.lower() not in EXTENSIONS: raise HTTPException(415, '不支持的文件格式')
        return filename

    def document_content(kind, content):
        if kind == 'document' and isinstance(content, dict):
            return validate_document(content)
        if kind in ('document', 'text'):
            if not isinstance(content, str) or len(content) > 200000:
                raise HTTPException(400, '文档内容最多 20 万字')
            return content, content
        if kind == 'sheet':
            if not isinstance(content, list) or len(content) > 100 or any(
                not isinstance(row, list) or len(row) > 26 or any(not isinstance(cell, str) or len(cell) > 5000 for cell in row)
                for row in content
            ):
                raise HTTPException(400, '表格最多 100 行、26 列，每格最多 5000 字')
            return content, ' '.join(cell for row in content for cell in row)
        if kind == 'slides':
            if not isinstance(content, list) or len(content) > 50 or any(
                not isinstance(slide, dict) or not isinstance(slide.get('title'), str)
                or not isinstance(slide.get('body'), str) or len(slide['title']) > 200 or len(slide['body']) > 10000
                for slide in content
            ):
                raise HTTPException(400, '幻灯片最多 50 页，每页正文最多 1 万字')
            return [{'title': slide['title'], 'body': slide['body']} for slide in content], ' '.join(
                slide['title'] + ' ' + slide['body'] for slide in content
            )
        raise HTTPException(400, '不支持的文档类型')

    def document_bytes(kind, content):
        if kind == 'document' and not isinstance(content, dict):
            raise HTTPException(400, '请使用结构化文档内容')
        if kind == 'document':
            validate_document(content, for_write=True)
        normalized, extracted = document_content(kind, content)
        payload = normalized.encode('utf-8') if kind == 'text' else json.dumps(
            {'kind': kind, 'content': normalized}, ensure_ascii=False, separators=(',', ':')
        ).encode('utf-8')
        if len(payload) > int(os.getenv('MAX_UPLOAD_BYTES', 20*1024*1024)):
            raise HTTPException(413, '文档超过大小限制')
        return payload, extracted

    @app.post('/api/v1/me/drive/documents', status_code=201)
    def create_document(payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        kind = payload.get('kind')
        if kind not in NATIVE_FORMATS:
            raise HTTPException(400, '请选择文档、表格或幻灯片')
        folder_id = payload.get('folderId') or ''
        folder_for(db, folder_id, user)
        title = name(payload.get('title'))
        extension, category = NATIVE_FORMATS[kind]
        initial = new_document() if kind == 'document' else [['', '', ''] for _ in range(8)] if kind == 'sheet' else [{'title': '', 'body': ''}]
        content, extracted = document_bytes(kind, initial)
        base, index = title, 1
        while db.scalar(select(Resource.id).where(Resource.owner_id == user.id, Resource.folder_id == (folder_id or None), Resource.title == title)):
            index += 1
            title = f'{base[:185]} ({index})'
        storage = str(uuid4())
        destination = uploads / storage
        destination.write_bytes(content)
        try:
            row = Resource(owner_id=user.id, folder_id=folder_id or None, title=title, type=category,
                           description='', visibility='private', file_name=title[:255-len(extension)] + extension,
                           storage_name=storage, size=len(content), extracted_text=extracted)
            db.add(row); db.flush()
            db.add(ResourceVersion(resource_id=row.id, version=1, file_name=row.file_name,
                                   storage_name=storage, size=len(content), note='新建文档', author_id=user.id))
            db.commit()
            return result(file_json(db, row, user))
        except Exception:
            db.rollback(); destination.unlink(missing_ok=True); raise

    @app.get('/api/v1/resources/{resource_id}/document')
    def get_document(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user)
        extension = Path(row.file_name).suffix.lower()
        kind = next((candidate for candidate, (suffix, _) in NATIVE_FORMATS.items() if suffix == extension), None)
        if not kind and extension not in ('.txt', '.md'):
            raise HTTPException(415, '此文件暂不支持文档工作区')
        location = uploads / row.storage_name
        if not location.is_file():
            raise HTTPException(404, '文件暂时不可用')
        try:
            raw = location.read_bytes()
            if kind:
                stored = json.loads(raw.decode('utf-8'))
                if not isinstance(stored, dict) or stored.get('kind') != kind:
                    raise ValueError('文档类型不匹配')
                content, _ = document_content(kind, stored['content'])
            else:
                content = raw.decode('utf-8-sig')
        except (UnicodeError, ValueError, KeyError, TypeError, HTTPException):
            raise HTTPException(415, '文件编码或文档结构无法读取')
        modified_at = db.scalar(select(ResourceVersion.created_at).where(
            ResourceVersion.resource_id == row.id
        ).order_by(ResourceVersion.version.desc()).limit(1))
        return result({'id': row.id, 'title': row.title, 'kind': kind or 'text', 'content': content,
                       'version': row.version, 'canEdit': row.owner_id == user.id,
                       'owner': user.display_name if row.owner_id == user.id else ctx['name'](db, row.owner_id),
                       'modifiedAt': iso(modified_at)})

    @app.put('/api/v1/resources/{resource_id}/document')
    def save_document(resource_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        extension = Path(row.file_name).suffix.lower()
        kind = next((candidate for candidate, (suffix, _) in NATIVE_FORMATS.items() if suffix == extension), None)
        if not kind and extension not in ('.txt', '.md'):
            raise HTTPException(415, '此文件暂不支持在线编辑')
        expected_version = payload.get('version')
        if type(expected_version) is not int or expected_version < 1:
            raise HTTPException(400, '文档版本号无效')
        if expected_version != row.version:
            raise HTTPException(409, '文档已在其他页面更新，请刷新后再编辑')
        content, extracted = document_bytes(kind or 'text', payload.get('content'))
        storage = str(uuid4())
        destination = uploads / storage
        destination.write_bytes(content)
        try:
            changed = db.execute(update(Resource).where(
                Resource.id == row.id, Resource.version == expected_version, Resource.archived.is_(False)
            ).values(version=expected_version + 1, storage_name=storage,
                     size=len(content), extracted_text=extracted).execution_options(synchronize_session=False)).rowcount
            if changed != 1:
                raise HTTPException(409, '文档已在其他页面更新，请刷新后再编辑')
            version_row = ResourceVersion(resource_id=row.id, version=expected_version + 1, file_name=row.file_name,
                                          storage_name=storage, size=len(content), note='在线编辑', author_id=user.id)
            db.add(version_row)
            db.commit()
            return result({'id': row.id, 'version': expected_version + 1, 'modifiedAt': iso(version_row.created_at)})
        except Exception:
            db.rollback(); destination.unlink(missing_ok=True); raise

    async def save_upload(db, user, file, folder_id, title, category, description, key, version_resource=None, note='', legacy_team=None):
        folder_for(db, folder_id, user)
        content = await file.read(int(os.getenv('MAX_UPLOAD_BYTES', 20*1024*1024))+1)
        filename = validate_file(file.filename, content)
        if category not in ('paper', 'note', 'slides', 'other', 'tutorial', 'experience', 'template'): raise HTTPException(400, '资料分类无效')
        title = name(title or filename[:200])
        scope = version_resource.id if version_resource else 'file'
        receipt_key = f'{user.id}:{scope}:{key}' if key else ''
        fingerprint = hashlib.sha256(content + json.dumps([filename, folder_id, title, category, description, note], ensure_ascii=False).encode()).hexdigest()
        if receipt_key:
            receipt = db.get(UploadReceipt, receipt_key)
            if receipt and receipt.created_at.replace(tzinfo=utcnow().tzinfo) > utcnow()-timedelta(hours=24):
                if receipt.fingerprint != fingerprint: raise HTTPException(409, '同一上传标识不能用于不同内容')
                return receipt.result
            if receipt: db.delete(receipt); db.flush()
        storage = str(uuid4())
        destination = uploads / storage
        destination.write_bytes(content)
        try:
            if version_resource:
                row = version_resource
                previous_version = row.version
                if not db.scalar(select(ResourceVersion.id).where(ResourceVersion.resource_id == row.id, ResourceVersion.version == row.version)):
                    db.add(ResourceVersion(resource_id=row.id, version=row.version, file_name=row.file_name, storage_name=row.storage_name, size=row.size, note='初始版本', author_id=row.owner_id))
                changed = db.execute(update(Resource).where(
                    Resource.id == row.id, Resource.version == previous_version, Resource.archived.is_(False)
                ).values(version=previous_version + 1, file_name=filename, storage_name=storage,
                         size=len(content), extracted_text=extract_document_text(filename, content)
                         ).execution_options(synchronize_session=False)).rowcount
                if changed != 1:
                    raise HTTPException(409, '文件已在其他页面更新，请刷新后重试')
                db.expire(row)
            else:
                base, index = title, 1
                while db.scalar(select(Resource.id).where(Resource.owner_id == user.id, Resource.folder_id == (folder_id or None), Resource.title == title)):
                    index += 1; title = f'{base[:185]} ({index})'
                row = Resource(owner_id=user.id, team_id=legacy_team, folder_id=folder_id or None, title=title, type=category, description=description, visibility='private', file_name=filename, storage_name=storage, size=len(content), extracted_text=extract_document_text(filename, content))
                db.add(row); db.flush()
            version = ResourceVersion(resource_id=row.id, version=row.version, file_name=filename, storage_name=storage, size=len(content), note=note, author_id=user.id)
            db.add(version); db.flush()
            value = {'id': version.id, 'resourceId': row.id, 'version': row.version} if version_resource else file_json(db, row, user)
            if receipt_key: db.add(UploadReceipt(key=receipt_key, fingerprint=fingerprint, result=value))
            db.commit()
            return value
        except IntegrityError:
            db.rollback(); destination.unlink(missing_ok=True)
            receipt = db.get(UploadReceipt, receipt_key) if receipt_key else None
            if receipt and receipt.fingerprint == fingerprint: return receipt.result
            raise HTTPException(409, '上传状态已变化，请刷新后重试')
        except Exception:
            db.rollback(); destination.unlink(missing_ok=True); raise

    @app.post('/api/v1/me/drive/files', status_code=201)
    async def upload(file: UploadFile = File(), folderId: str = Form(''), title: str = Form(''), type: str = Form('other'), description: str = Form('', max_length=50000), idempotency_key: str = Header('', alias='Idempotency-Key', max_length=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        return result(await save_upload(db, user, file, folderId, title, type, description, idempotency_key))

    @app.post('/api/v1/teams/{team_id}/resources')
    async def legacy_upload(team_id: str, file: UploadFile = File(), title: str = Form(''), type: str = Form('other'), description: str = Form(''), meetingId: str = Form(''), taskId: str = Form(''), user: User = Depends(current_user), db: Session = Depends(get_db)):
        ctx['team_member'](db, team_id, user)
        for kind, ident in [('meeting', meetingId), ('task', taskId)]:
            if ident:
                target = db.get(Meeting if kind == 'meeting' else Task, ident)
                if not target or target.team_id != team_id: raise HTTPException(400, '关联内容不属于当前课题组')
                target_for(db, kind, ident, user)
        value = await save_upload(db, user, file, '', title, type, description, '', legacy_team=team_id)
        row = db.get(Resource, value['id']); row.meeting_id, row.task_id = meetingId or None, taskId or None
        db.commit()
        return result(value)

    @app.post('/api/v1/resources/{resource_id}/versions')
    async def version_upload(resource_id: str, file: UploadFile = File(), note: str = Form('', max_length=50000), idempotency_key: str = Header('', alias='Idempotency-Key', max_length=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        return result(await save_upload(db, user, file, row.folder_id, row.title, row.type, row.description, idempotency_key, row, note))

    @app.get('/api/v1/resources/{resource_id}/shares')
    def shares(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        items = [{'id': s.id, 'userId': s.user_id, 'displayName': ctx['name'](db, s.user_id), 'teamId': s.team_id, 'permission': 'read', 'active': bool(valid_share(db, s, row)), 'createdAt': iso(s.created_at)} for s in db.scalars(select(ResourceShare).where(ResourceShare.resource_id == row.id))]
        return result({'direct': {'items': items}, 'legacyAccess': {'teamId': row.team_id, 'active': row.visibility == 'team'}})

    @app.put('/api/v1/resources/{resource_id}/shares/{user_id}')
    def share(resource_id: str, user_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        team_id = payload.get('teamId')
        if payload.get('permission') != 'read' or user_id == user.id or not member_of(db, team_id, user.id) or not member_of(db, team_id, user_id): raise HTTPException(400, '只能只读共享给同课题组的有效成员')
        s = db.scalar(select(ResourceShare).where(ResourceShare.resource_id == row.id, ResourceShare.user_id == user_id, ResourceShare.team_id == team_id))
        if not s:
            s = ResourceShare(resource_id=row.id, user_id=user_id, team_id=team_id); db.add(s)
        s.active = True; db.commit()
        return result({'id': s.id, 'userId': user_id, 'teamId': team_id, 'permission': 'read', 'active': True})

    @app.delete('/api/v1/resources/{resource_id}/shares/{user_id}')
    def revoke(resource_id: str, user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = resource_for(db, resource_id, user, True)
        for s in db.scalars(select(ResourceShare).where(ResourceShare.resource_id == row.id, ResourceShare.user_id == user_id)): s.active = False
        db.commit(); return result(None)

    @app.post('/api/v1/tasks/{target_id}/resources')
    @app.post('/api/v1/meetings/{target_id}/resources')
    def reference(target_id: str, request: Request, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        kind = 'task' if '/tasks/' in request.url.path else 'meeting'
        target_for(db, kind, target_id, user)
        row, _ = resource_for(db, str(payload.get('resourceId', '')), user)
        ref = db.scalar(select(ResourceReference).where(ResourceReference.target_type == kind, ResourceReference.target_id == target_id, ResourceReference.resource_id == row.id))
        if not ref:
            ref = ResourceReference(target_type=kind, target_id=target_id, resource_id=row.id); db.add(ref); db.commit()
        return result({'id': ref.id, 'resourceId': ref.resource_id, 'targetType': kind, 'targetId': target_id, 'createdAt': iso(ref.created_at)})

    @app.delete('/api/v1/tasks/{target_id}/resources/{reference_id}')
    @app.delete('/api/v1/meetings/{target_id}/resources/{reference_id}')
    def remove_reference(target_id: str, reference_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        kind = 'task' if '/tasks/' in request.url.path else 'meeting'
        target_for(db, kind, target_id, user)
        row = db.get(ResourceReference, reference_id)
        if not row or row.target_type != kind or row.target_id != target_id: raise HTTPException(404, '引用不存在')
        db.delete(row); db.commit(); return result(None)

    @app.post('/api/v1/me/drive/questions')
    @app.post('/api/v1/teams/{team_id}/questions')
    def questions(payload: dict = Body(), team_id: str = '', user: User = Depends(current_user), db: Session = Depends(get_db)):
        if team_id: ctx['team_member'](db, team_id, user)
        question = ctx['text_value'](payload, 'question', required=True, maximum=500)
        ids = payload.get('resourceIds', [])
        if not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(x, str) for x in ids): raise HTTPException(400, '最多选择 100 份资料')
        if ids:
            rows = [resource_for(db, rid, user)[0] for rid in dict.fromkeys(ids)]
            if team_id and any(r.team_id != team_id for r in rows): raise HTTPException(404, '资料不属于当前课题组')
        else:
            rows = available_rows(db, user, 'all', '')
            if team_id: rows = [r for r in rows if r.team_id == team_id]
        rows = [r for r in rows if r.extracted_text]
        if len(rows) > 100: raise HTTPException(400, '可检索资料超过 100 份，请明确选择本次使用的文件')
        try: return result(assistant.answer(question, rows))
        except AssistantUnavailable as error: raise HTTPException(503, str(error)) from error

    return {'file_json': file_json}
