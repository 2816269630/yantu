import { selectField } from '../../components/forms.js';
import { openModal } from '../../components/modal.js';
import { btn } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { bytes, esc } from '../../core/format.js';
import { renderPage } from '../../core/router.js';
import { state, typeNames } from '../../core/state.js';
import { driveFolderOptions } from './browser.js';

let uploadQueue = [],
  uploadRunning = false;

function clearUploadQueue() {
  for (const item of uploadQueue) item.xhr?.abort();
  uploadQueue = [];
  uploadRunning = false;
}

async function openCloudUpload(target = null) {
  const config = await api('/me/drive/config'),
    tree = await api('/me/drive/folders/tree');
  state.uploadTarget = target;
  openModal(
    '上传到我的云盘',
    `<p class="notice">文件默认私有。${target ? '上传成功后可选择明确授权，再引用至' + (target.kind === 'meeting' ? '组会' : '任务') + '。' : ''}</p><div class="form-stack mt16">${selectField('目标文件夹', 'uploadFolder', driveFolderOptions(tree.items), state.driveFolder || '')}${selectField(
      '资料分类',
      'uploadType',
      Object.entries(typeNames).map(([id, name]) => ({ id, name })),
    )}<p class="small">每个文件最多 ${bytes(config.maxUploadBytes)}；支持 ${config.allowedExtensions.join('、')}。</p><label class="drive-drop" id="uploadDrop">点击选择或将多个文件拖到这里<input type="file" id="cloudFiles" multiple accept="${config.allowedExtensions.join(',')}"></label><div id="uploadQueue" aria-live="polite"></div><div class="form-actions">${btn('重试失败项', 'cloud-retry')}${btn('完成', 'cloud-upload-done', '', 'primary')}</div></div>`,
  );
  $('#cloudFiles').addEventListener('change', (e) => enqueueFiles(e.target.files, config));
  const drop = $('#uploadDrop');
  drop.addEventListener('dragover', (e) => {
    e.preventDefault();
    drop.classList.add('dragging');
  });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('dragging');
    enqueueFiles(e.dataTransfer.files, config);
  });
  renderUploadQueue();
}

function enqueueFiles(files, config) {
  const folder = $('[name=uploadFolder]').value,
    category = $('[name=uploadType]').value;
  const folderName = $('[name=uploadFolder]').selectedOptions[0].textContent;
  for (const file of files) {
    let error = '';
    const extension = '.' + file.name.split('.').pop().toLowerCase();
    if (!file.size) error = '不能上传空文件';
    else if (file.size > config.maxUploadBytes) error = '文件超过大小限制';
    else if (!config.allowedExtensions.includes(extension)) error = '不支持的文件格式';
    uploadQueue.push({
      file,
      folder,
      folderName,
      category,
      key: crypto.randomUUID(),
      status: error ? 'invalid' : 'waiting',
      error,
      owner: state.user.id,
      target: state.uploadTarget,
    });
  }
  renderUploadQueue();
  processUploadQueue();
}

function renderUploadQueue() {
  const box = $('#uploadQueue');
  if (!box) return;
  box.innerHTML = uploadQueue
    .map(
      (x) =>
        `<div class="upload-item"><strong>${esc(x.file.name)}</strong><span class="small">${esc(x.folderName)} · ${esc({ waiting: '等待中', uploading: '上传中', success: '成功', failed: '失败', invalid: '无法上传' }[x.status])}${x.status === 'uploading' && x.progress != null ? ' ' + x.progress + '%' : ''}</span>${x.error ? `<p class="danger-text">${esc(x.error)}</p>` : ''}${x.status === 'success' && x.target ? btn('选择授权并引用', 'cloud-link', x.result.id) : ''}</div>`,
    )
    .join('');
}

function uploadOne(item) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    item.xhr = xhr;
    xhr.open('POST', '/api/v1/me/drive/files');
    xhr.withCredentials = true;
    xhr.setRequestHeader('Idempotency-Key', item.key);
    xhr.timeout = 180000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        item.progress = Math.round((e.loaded / e.total) * 100);
        renderUploadQueue();
      }
    };
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300 && data?.data) resolve(data.data);
      else reject(new Error(data?.message || `上传失败（${xhr.status}）`));
    };
    xhr.onerror = () => reject(new Error('网络错误，请重试'));
    xhr.ontimeout = () => reject(new Error('上传超时，请重试'));
    xhr.onabort = () => reject(new Error('上传已取消'));
    const body = new FormData();
    body.append('file', item.file);
    body.append('folderId', item.folder);
    body.append('type', item.category);
    xhr.send(body);
  });
}

async function processUploadQueue() {
  if (uploadRunning) return;
  uploadRunning = true;
  try {
    for (const item of uploadQueue) {
      if (item.status !== 'waiting' || item.owner !== state.user?.id) continue;
      item.status = 'uploading';
      renderUploadQueue();
      try {
        item.result = await uploadOne(item);
        item.status = 'success';
        item.error = '';
      } catch (e) {
        item.status = 'failed';
        item.error = e.message;
      }
      renderUploadQueue();
    }
  } finally {
    uploadRunning = false;
    if (state.page === 'resources') renderPage();
  }
}
export {
  uploadQueue,
  uploadRunning,
  clearUploadQueue,
  openCloudUpload,
  enqueueFiles,
  renderUploadQueue,
  uploadOne,
  processUploadQueue,
};
