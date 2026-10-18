import { field, form, modalForm, selectField, values } from '../../components/forms.js';
import { icon } from '../../components/icons.js';
import { closeModal, openModal } from '../../components/modal.js';
import { btn, empty, head, link, toast } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $, $$ } from '../../core/dom.js';
import { bytes, enc, esc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { pages, state, typeNames } from '../../core/state.js';
import { openCloudUpload, processUploadQueue, uploadQueue } from './upload.js';

async function allDriveFiles(scope = 'all', extra = '') {
  let page = 1,
    items = [],
    data;
  do {
    data = await api(
      `/me/drive/available-resources?scope=${enc(scope)}&pageSize=100&page=${page++}${extra}`,
    );
    items.push(...data.items);
  } while (items.length < data.total);
  return items;
}

function driveFolderOptions(items) {
  const byId = new Map(items.map((x) => [x.id, x]));
  return [
    { id: '', name: '我的文件 / 根目录' },
    ...items
      .map((x) => {
        const names = [x.name];
        let p = byId.get(x.parentId),
          seen = new Set([x.id]);
        while (p && !seen.has(p.id)) {
          seen.add(p.id);
          names.unshift(p.name);
          p = byId.get(p.parentId);
        }
        return { id: x.id, name: '我的文件 / ' + names.join(' / ') };
      })
      .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
  ];
}

function driveUrl(scope = 'mine', folder = '', q = '', page = 1) {
  return 'resources/' + enc(JSON.stringify({ scope, folder, q, page }));
}

pages.resources = async (raw) => {
  let view = { scope: 'mine', folder: '', q: '', page: 1 };
  try {
    Object.assign(view, JSON.parse(decodeURIComponent(raw || '')));
  } catch {}
  if (!['mine', 'shared'].includes(view.scope)) view.scope = 'mine';
  const seq = state.sequence;
  const [tree, data] = await Promise.all([
    api('/me/drive/folders/tree'),
    api(
      view.scope === 'mine' && !view.q
        ? `/me/drive/children?folderId=${enc(view.folder)}&page=${view.page}&pageSize=50`
        : `/me/drive/search?scope=${view.scope}&q=${enc(view.q)}&page=${view.page}&pageSize=50`,
    ),
  ]);
  if (seq !== state.sequence) return '';
  state.driveView = view;
  state.driveFolder = view.folder;
  state.driveReturn = driveUrl(view.scope, view.folder, view.q, view.page);
  state.data.driveItems = data.items;
  state.data.driveTree = tree.items;
  const folderOptions = driveFolderOptions(tree.items);
  const folders = folderOptions
    .map(
      (x) =>
        `<div style="padding-left:${Math.max(0, x.name.split(' / ').length - 2) * 14}px">${link(icon('folder') + ' ' + esc(x.id ? x.name.split(' / ').pop() : '我的文件'), driveUrl('mine', x.id), 'drive-tree-link ' + (view.scope === 'mine' && view.folder === x.id ? 'active' : ''))}</div>`,
    )
    .join('');
  const path = data.breadcrumbs || [
    { id: null, name: view.scope === 'mine' ? '个人全部目录' : '共享给我的' },
  ];
  return (
    head(
      '我的云盘',
      '个人文件按账号独立保存。共享和业务引用均不改变文件所有权。',
      view.scope === 'mine'
        ? btn(icon('plus') + '新建文件夹', 'cloud-new') +
            btn(icon('upload') + '上传文件', 'upload-resource', '', 'primary')
        : '',
    ) +
    `<nav class="section-tabs" aria-label="云盘视图">${link('我的文件', driveUrl('mine'), 'btn ' + (view.scope === 'mine' ? 'primary' : ''))}${link('共享给我的', driveUrl('shared'), 'btn ' + (view.scope === 'shared' ? 'primary' : ''))}</nav><div class="drive-layout"><details class="panel drive-tree" open><summary>我的目录</summary>${folders}</details><section class="stack"><form data-form="cloud-search" class="toolbar"><input class="input" name="q" value="${esc(view.q)}" placeholder="${view.scope === 'mine' ? '搜索个人全部目录' : '搜索有效共享文件'}" aria-label="搜索文件名称"><button class="btn" type="submit">搜索</button>${view.q ? link('清除', driveUrl(view.scope, view.folder), 'btn') : ''}</form><nav class="drive-breadcrumb" aria-label="文件位置">${path.map((x) => link(esc(x.name), driveUrl(view.scope, x.id || ''))).join('<span>/</span>')}</nav><div class="panel tablewrap"><table><thead><tr><th>名称</th><th>类型 / 大小</th><th>所有者 / 版本</th><th>操作</th></tr></thead><tbody>${data.items.length ? data.items.map((x) => driveRow(x, view)).join('') : `<tr><td colspan="4">${empty(view.q ? '没有搜索结果' : view.scope === 'shared' ? '暂无有效共享文件' : '此目录还是空的', view.q ? '换一个名称关键词试试。' : view.scope === 'shared' ? '文件所有者明确授权后会出现在这里。' : '新建文件夹或上传第一份文件。')}</td></tr>`}</tbody></table></div><div class="between"><span class="small">共 ${data.total} 项 · 第 ${view.page} 页</span><div>${view.page > 1 ? link('上一页', driveUrl(view.scope, view.folder, view.q, view.page - 1), 'btn') : ''}${view.page * 50 < data.total ? link('下一页', driveUrl(view.scope, view.folder, view.q, view.page + 1), 'btn') : ''}</div></div></section></div>`
  );
};

function driveRow(x, view) {
  const folder = x.kind === 'folder',
    own = folder || x.ownerId === state.user.id;
  return `<tr><td>${link(icon(folder ? 'folder' : 'file') + ' ' + esc(folder ? x.name : x.title), folder ? driveUrl('mine', x.id) : 'resource/' + enc(x.id), 'filename')}${view.q && own && !folder ? `<p class="small">${link(esc((x.location || []).map((p) => p.name).join(' / ')), driveUrl('mine', x.folderId || ''))}</p>` : ''}${!own ? '<p class="small">只读共享 · 可查看、预览、下载</p>' : ''}</td><td>${folder ? '文件夹' : `${esc(typeNames[x.type] || x.type)} · ${bytes(x.size)}`}</td><td>${folder ? '我' : `${esc(x.owner)} · v${esc(x.version)}`}</td><td><div class="flex wrap">${!folder ? btn('下载', 'download-resource', x.id, 'sm') : ''}${own ? btn('重命名', 'cloud-rename', x.id, 'sm') + btn('移动', 'cloud-move', x.id, 'sm') : ''}${folder ? btn('删除空目录', 'cloud-delete', x.id, 'sm') : own ? btn('共享', 'cloud-shares', x.id, 'sm') : ''}</div></td></tr>`;
}

async function cloudAction(action, id) {
  if (action === 'cloud-upload-for-target') {
    await openCloudUpload(state.referenceTarget);
    return true;
  }

  if (!action.startsWith('cloud-') && action !== 'attach-task' && action !== 'attach-meeting')
    return false;
  const item = state.data.driveItems?.find((x) => x.id === id),
    folder = item?.kind === 'folder';
  if (action === 'cloud-new')
    modalForm(
      '新建文件夹',
      'cloud-folder',
      field('名称', 'name', '', { required: true, max: 200 }),
      '创建',
    );
  if (action === 'cloud-rename')
    modalForm(
      folder ? '重命名文件夹' : '重命名文件',
      'cloud-rename',
      field('名称', 'name', folder ? item.name : item.title, { required: true, max: 200 }) +
        `<input type="hidden" name="kind" value="${folder ? 'folder' : 'file'}">`,
      '保存',
      id,
    );
  if (action === 'cloud-move') {
    const tree = await api('/me/drive/folders/tree');
    modalForm(
      '选择目标目录',
      'cloud-move',
      selectField(
        '目标目录',
        'folderId',
        driveFolderOptions(tree.items),
        folder ? item.parentId : item.folderId,
      ) + `<input type="hidden" name="kind" value="${folder ? 'folder' : 'file'}">`,
      '移动',
      id,
    );
  }
  if (action === 'cloud-delete')
    modalForm(
      '删除空文件夹',
      'cloud-delete',
      `<p>确认删除“${esc(item.name)}”？非空目录会被拒绝。</p>`,
      '删除',
      id,
    );
  if (action === 'cloud-shares') await openShares(id);
  if (action === 'cloud-revoke') {
    const [resource, user] = id.split(':');
    modalForm(
      '撤销直接共享',
      'cloud-revoke',
      `<p>撤销该文件对这个成员在所有课题组中的直接授权。若仍有原课题组共享，该成员可能继续可访问。</p>`,
      '撤销',
      resource + ':' + user,
    );
  }
  if (action === 'cloud-retry') {
    for (const x of uploadQueue)
      if (x.status === 'failed') {
        x.status = 'waiting';
        x.error = '';
      }
    processUploadQueue();
  }
  if (action === 'cloud-upload-done') {
    closeModal();
    await renderPage();
  }
  if (action === 'attach-task' || action === 'attach-meeting') {
    await openReferencePicker({ kind: action === 'attach-task' ? 'task' : 'meeting', id });
  }
  if (action === 'cloud-link') {
    const item = uploadQueue.find((x) => x.result?.id === id);
    if (item?.target) await openReferencePicker(item.target, id);
  }
  return true;
}

async function openShares(id) {
  const shares = await api(`/resources/${enc(id)}/shares`);
  const rows = shares.direct.items;
  openModal(
    '文件共享与授权',
    `<p class="notice">仅授权此文件的查看、预览、下载和个人阅读状态。接收人不能修改或再次共享。${shares.legacyAccess.active ? '本文件仍通过原课题组共享可访问，撤销直接授权不关闭这一来源。' : ''}</p>${rows.map((x) => `<div class="row"><div class="row-main"><strong>${esc(x.displayName)}</strong><p>课题组 ${esc(x.teamId)} · ${x.active ? '有效只读授权' : '已失效'}</p></div>${x.active ? btn('撤销', 'cloud-revoke', id + ':' + x.userId) : ''}</div>`).join('')}${
      state.team
        ? form(
            'cloud-share',
            selectField(
              '授权成员',
              'userId',
              state.members
                .filter((x) => x.id !== state.user.id)
                .map((x) => ({ id: x.id, name: x.name })),
            ) +
              `<p class="small">授权上下文：${esc(state.team.name)}，离组后失效，重新加入需要重新授权。</p>`,
            '确认只读授权',
            id,
          )
        : '<p class="small mt16">加入课题组后可选择组内成员共享。</p>'
    }`,
  );
}

async function openReferencePicker(target, selected = '') {
  state.referenceTarget = target;
  const files = await allDriveFiles('all', `&targetType=${target.kind}&targetId=${enc(target.id)}`);
  state.data.referenceFiles = files;
  openModal(
    '从我的云盘引用材料',
    `<p class="notice">引用保持原文件 ID，不自动扩大权限。只对勾选的无权成员新增授权。授权成功但关联失败时，授权会保留，可到云盘撤销。</p>${form(
      'cloud-reference',
      selectField(
        '文件',
        'resourceId',
        files.map((x) => ({ id: x.id, name: x.title + ' · ' + x.owner })),
        selected,
      ) + `<div id="referenceAudience"></div>`,
      '确认授权并引用',
    )}${btn('先上传新文件', 'cloud-upload-for-target')}`,
  );
  const sel = $('[name=resourceId]');
  sel?.addEventListener('change', renderAudience);
  renderAudience();
}

function renderAudience() {
  const selected = $('[name=resourceId]')?.value,
    item = state.data.referenceFiles.find((x) => x.id === selected);
  const box = $('#referenceAudience');
  if (!box) return;
  box.innerHTML = item
    ? (item.audience || [])
        .map(
          (x) =>
            `<div class="row"><span>${esc(x.displayName)}：${x.canRead ? '已可访问' : '当前无权访问'}</span>${!x.canRead && item.ownerId === state.user.id ? `<label><input name="grantUser" type="checkbox" value="${esc(x.userId)}"> 明确授予只读权限</label>` : ''}</div>`,
        )
        .join('') +
      (item.ownerId !== state.user.id
        ? '<p class="small">你不是所有者；无权成员需要联系所有者获取授权。</p>'
        : '')
    : '';
}

async function cloudSubmit(f) {
  const type = f.dataset.form;
  if (!type.startsWith('cloud-')) return false;
  const d = values(f),
    id = f.dataset.id;
  let refresh = true;
  if (type === 'cloud-search') {
    navigate(driveUrl(state.driveView.scope, state.driveView.folder, d.q));
    return true;
  }
  if (type === 'cloud-folder')
    await api('/me/drive/folders', 'POST', { name: d.name, parentId: state.driveFolder || null });
  if (type === 'cloud-rename')
    await api(
      d.kind === 'folder' ? `/me/drive/folders/${enc(id)}` : `/resources/${enc(id)}`,
      'PATCH',
      d.kind === 'folder' ? { name: d.name } : { title: d.name },
    );
  if (type === 'cloud-move')
    await api(
      d.kind === 'folder' ? `/me/drive/folders/${enc(id)}` : `/resources/${enc(id)}`,
      'PATCH',
      d.kind === 'folder' ? { parentId: d.folderId || null } : { folderId: d.folderId || null },
    );
  if (type === 'cloud-delete') await api(`/me/drive/folders/${enc(id)}`, 'DELETE');
  if (type === 'cloud-share') {
    await api(`/resources/${enc(id)}/shares/${enc(d.userId)}`, 'PUT', {
      permission: 'read',
      teamId: state.team.id,
    });
    toast('只读授权已保存');
    await openShares(id);
    return true;
  }
  if (type === 'cloud-revoke') {
    const [r, u] = id.split(':');
    await api(`/resources/${enc(r)}/shares/${enc(u)}`, 'DELETE');
    toast('直接授权已撤销；原课题组共享范围保持');
    await openShares(r);
    return true;
  }
  if (type === 'cloud-reference') {
    const target = state.referenceTarget,
      item = state.data.referenceFiles.find((x) => x.id === d.resourceId);
    let granted = 0;
    try {
      for (const box of $$('input[name=grantUser]:checked', f)) {
        await api(`/resources/${enc(item.id)}/shares/${enc(box.value)}`, 'PUT', {
          permission: 'read',
          teamId: state.team.id,
        });
        granted++;
      }
      await api(
        `/${target.kind === 'task' ? 'tasks' : 'meetings'}/${enc(target.id)}/resources`,
        'POST',
        { resourceId: item.id },
      );
    } catch (e) {
      if (granted)
        e.message = '授权已保存，关联未完成：' + e.message + '。可重试关联或到云盘撤销新增授权。';
      throw e;
    }
  }
  closeModal();
  toast('操作已保存');
  if (refresh) await renderPage();
  return true;
}
export {
  allDriveFiles,
  driveFolderOptions,
  driveUrl,
  driveRow,
  cloudAction,
  openShares,
  openReferencePicker,
  renderAudience,
  cloudSubmit,
};
