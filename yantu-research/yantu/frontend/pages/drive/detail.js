import { icon } from '../../components/icons.js';
import { btn, empty, head, link, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { bytes, datetime, enc, esc } from '../../core/format.js';
import { pages, scopeNames, state, typeNames } from '../../core/state.js';

function resourcePreview(r) {
  if (!r.previewable)
    return `<section class="panel padded"><h2>在线查看</h2><div class="notice mt16">该文件格式暂不支持浏览器在线预览，请使用右上角“下载文件”查看。PDF、图片、文本、音频和视频可直接在线打开。</div></section>`;
  const progress = r.readingProgress || {},
    base = `/api/v1/resources/${enc(r.id)}/preview`,
    type = r.previewType || '';
  if (type === 'application/pdf')
    return `<section class="panel padded"><div class="between"><div><h2>论文阅读</h2><p class="section-note mt16">使用全屏阅读器，自动记录当前页，笔记会随输入自动保存。</p></div>${btn('新窗口阅读 ↗', 'open-reader', r.id, 'primary')}</div></section>`;
  if (type.startsWith('image/'))
    return `<section class="panel padded"><div class="between mb16"><h2>在线查看</h2><a class="textbutton" href="${base}" target="_blank" rel="noopener">新窗口打开 ↗</a></div><div class="resource-preview image" data-reading-scroll><img src="${base}" alt="${esc(r.title)}"></div></section>`;
  if (type.startsWith('audio/'))
    return `<section class="panel padded"><h2 class="mb16">在线查看</h2><audio class="media-preview" src="${base}" controls data-reading-media></audio></section>`;
  if (type.startsWith('video/'))
    return `<section class="panel padded"><h2 class="mb16">在线查看</h2><video class="media-preview" src="${base}" controls data-reading-media></video></section>`;
  return `<section class="panel padded"><div class="between mb16"><h2>在线查看</h2><a class="textbutton" href="${base}" target="_blank" rel="noopener">新窗口打开 ↗</a></div><iframe class="resource-preview-frame" src="${base}" title="${esc(r.title)}在线预览" data-reading-frame></iframe></section>`;
}

function resourceRows(items) {
  return items.length
    ? items
        .map(
          (r) =>
            `<tr><td><div class="flex"><span class="resource-icon ${esc(r.type)}">${esc((r.fileName?.split('.').pop() || (r.type === 'paper' ? 'PDF' : 'DOC')).slice(0, 5).toUpperCase())}</span><div>${link(esc(r.title), 'resource/' + enc(r.id), 'filename')}<div class="small text-clamp">${esc(r.description || '查看资料说明与版本')}</div></div></div></td><td>${tag(typeNames[r.type] || r.type, 'blue')}</td><td class="nowrap">${esc(r.owner)}</td><td class="nowrap"><span class="small">v${esc(r.version || 1)}</span></td><td class="nowrap"><span class="small">${esc(scopeNames[r.visibility] || '课题组')}</span></td><td>${link(icon('right'), 'resource/' + enc(r.id), 'iconbtn')}</td></tr>`,
        )
        .join('')
    : `<tr><td colspan="6">${empty('资料库还是空的', '上传第一份论文、笔记或组会材料，并说明如何使用它。', btn('上传资料', 'upload-resource', '', 'primary'), 'folder')}</td></tr>`;
}

pages.resource = async (id) => {
  const [r, versions, readingProgress] = await Promise.all([
    api(`/resources/${enc(id)}`),
    list(`/resources/${enc(id)}/versions`),
    api(`/resources/${enc(id)}/reading-progress`),
  ]);
  r.readingProgress = readingProgress || {};
  state.data.resource = r;
  const canEdit = r.canEdit ?? r.ownerId === state.user.id;
  return (
    link(icon('back') + '返回我的云盘', state.driveReturn || 'resources', 'textbutton mb16') +
    head(
      r.title,
      `${typeNames[r.type] || r.type} · ${r.owner}维护`,
      `${canEdit ? btn('编辑说明', 'edit-resource', id) + btn(icon('upload') + '上传新版本', 'resource-version', id) + btn('共享管理', 'cloud-shares', id) : ''}${r.previewType === 'application/pdf' ? btn('新窗口阅读 ↗', 'open-reader', id, 'primary') : ''}${btn(icon('download') + '下载文件', 'download-resource', id, r.previewType === 'application/pdf' ? '' : 'primary')}`,
    ) +
    `<div class="grid2"><div class="stack">${resourcePreview(r)}<section class="panel padded"><div class="flex wrap mb16">${tag(typeNames[r.type] || r.type, 'blue')}${tag(scopeNames[r.visibility] || '课题组')}${(r.tags || []).map((t) => tag(t)).join('')}</div><h2>阅读建议与使用说明</h2><div class="rich-section">${para(r.description || '维护人还没有补充阅读建议。')}</div><div class="divider"></div><div class="resource-detail-grid"><div><p class="small">文件名称</p><p class="body-text">${esc(r.fileName)}</p></div><div><p class="small">文件大小</p><p>${bytes(r.size)}</p></div></div></section><section class="panel padded"><h2 class="mb16">版本记录</h2>${
      versions.length
        ? [...versions]
            .reverse()
            .map(
              (v) =>
                `<div class="version-item"><div class="between"><h3>v${esc(v.version || v.number || 1)} · ${esc(v.owner || v.author || r.owner)}</h3>${btn('下载', 'download-version', v.id, 'sm')}</div><p class="small">${v.createdAt ? datetime(v.createdAt) : ''} · ${bytes(v.size)}</p><p class="mt16">${esc(v.note || '首次上传')}</p></div>`,
            )
            .join('')
        : '<p class="small">当前文件为初始版本</p>'
    }</section></div><aside class="stack"><section class="panel padded"><h3>关联内容</h3><div class="detail-list mt16">${r.meetingId ? link(icon('calendar') + '关联组会' + icon('right'), 'meeting/' + enc(r.meetingId), 'list-link') : ''}${r.taskId ? link(icon('tasks') + '关联任务' + icon('right'), 'task/' + enc(r.taskId), 'list-link') : ''}${!r.meetingId && !r.taskId ? '<p class="small">未关联组会或任务</p>' : ''}</div></section><section class="panel padded"><div class="flex mb8">${icon('lock')}<h3>可见范围</h3></div><p class="section-note">${r.visibility === 'private' ? '所有者及获得明确只读授权的成员可访问；引用本身不会扩大访问范围。' : '保留原课题组共享范围；撤销直接共享不关闭原课题组访问。'}下载与科研助手检索均遵守此权限。</p></section></aside></div>`
  );
};
export { resourcePreview, resourceRows };
