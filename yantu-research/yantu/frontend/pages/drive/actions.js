import { field, modalForm } from '../../components/forms.js';
import { closeModal } from '../../components/modal.js';
import { toast } from '../../components/ui.js';
import { api, download } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { enc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { state, teamUrl } from '../../core/state.js';
import { resourceRows } from './detail.js';
import { openCloudUpload } from './upload.js';

async function handleDriveAction(action, id, source) {
  if (action === 'upload-resource' || action === 'meeting-upload')
    return openCloudUpload(action === 'meeting-upload' ? { kind: 'meeting', id } : null);
  if (action === 'edit-resource') {
    const r = state.data.resource;
    return modalForm(
      '编辑资料说明',
      'edit-resource',
      field('资料标题', 'title', r.title, { required: true }) +
        field('阅读建议与说明', 'description', r.description, { textarea: true }) +
        `<p class="small">访问权限通过共享管理设置。</p>` +
        field('标签（逗号分隔）', 'tags', (r.tags || []).join(',')),
      '保存',
      id,
    );
  }
  if (action === 'resource-version')
    return modalForm(
      '上传新版本',
      'resource-version',
      field('版本说明', 'note', '', { textarea: true }) +
        '<div class="field"><label for="f-file">选择新文件</label><input class="input" id="f-file" name="file" type="file" required></div>',
      '上传版本',
      id,
    );
  if (action === 'download-version')
    return download(
      `/resources/${enc(state.data.resource.id)}/download?versionId=${enc(id)}`,
      state.data.resource.fileName,
    );
  if (action === 'download-resource')
    return download(`/resources/${enc(id)}/download`, state.data.resource?.fileName || '科研资料');
  if (action === 'open-reader') {
    window.open(`/reader.html?id=${enc(id)}`, `research-reader-${id}`, 'noopener');
    return;
  }
  if (action === 'save-reading-page') {
    const input = $('[data-reading-page]'),
      page = Math.max(1, Number(input?.value) || 1);
    await api(`/resources/${enc(id)}/reading-progress`, 'PATCH', { page });
    const frame = $('.resource-preview-frame');
    if (frame) frame.src = `/api/v1/resources/${enc(id)}/preview#page=${page}`;
    toast(`已保存第 ${page} 页，下次将从这里继续`);
    return;
  }
  if (action === 'resource-filter') {
    const items =
      id === 'all' ? state.data.resources : state.data.resources.filter((r) => r.type === id);
    $('#resourceRows').innerHTML = resourceRows(items);
    return;
  }
}

async function submitDriveForm(type, data, id, formElement) {
  let result;
  if (type === 'resource-upload') {
    const body = new FormData(formElement);
    result = await api(teamUrl('/resources'), 'POST', body);
    closeModal();
    navigate('resource/' + result.id);
  }
  if (type === 'edit-resource') {
    data.tags = data.tags
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    await api(`/resources/${enc(id)}`, 'PATCH', data);
    closeModal();
    await renderPage();
  }
  if (type === 'resource-version') {
    await api(`/resources/${enc(id)}/versions`, 'POST', new FormData(formElement));
    closeModal();
    await renderPage();
  }
}
export { handleDriveAction, submitDriveForm };
