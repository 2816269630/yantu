import { field, form, selectField } from '../../components/forms.js';
import { icon } from '../../components/icons.js';
import { closeModal, openModal } from '../../components/modal.js';
import { btn, empty, para, tag, toast } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { datetime, enc, esc } from '../../core/format.js';
import { renderPage } from '../../core/router.js';
import { state, teamUrl } from '../../core/state.js';

async function renderHandovers() {
  const items = await list(teamUrl('/handovers'));
  state.data.handovers = items;
  const records = items.map((item) => {
    const accepted = item.status === 'accepted' || item.acceptedAt;
    return `<article class="handover-record"><div class="between mb16"><h3>${esc(item.title)}</h3>${tag(accepted ? '已接收' : '待接收', accepted ? 'green' : 'orange')}</div><p class="small mb16">${esc(item.fromUserName || item.fromName || item.author || '交接人')} → ${esc(item.toUserName || item.toName || '接收人')} · ${datetime(item.createdAt)}</p>${para(item.content)}<p class="small mt16">${(item.taskIds || []).length} 项关联任务 · ${(item.resourceIds || []).length} 份资料</p>${item.toUserId === state.user.id && !accepted ? `<div class="form-actions">${btn('确认接收交接', 'accept-handover', item.id, 'primary')}</div>` : ''}</article>`;
  });
  return `<section class="panel"><div class="panelhead"><h2>毕业与资料交接</h2>${btn(icon('plus') + '发起交接', 'create-handover', '', 'primary')}</div><p class="section-note handover-note">交接保留说明与关联清单；任务分工以任务页为准，资料须由所有者明确共享。</p>${items.length ? records.join('') : empty('让研究在交接后继续', '记录未解决问题、关联任务和资料，指定接收人。', btn('发起第一次交接', 'create-handover', '', 'primary'), 'history')}</section>`;
}

function referenceOptions(label, name, items, emptyLabel) {
  return `<fieldset class="handover-picker"><legend>${esc(label)}</legend><p class="helptext">可选，最多 100 项</p><div class="handover-options">${items.length ? items.map((item) => `<label class="handover-option"><input type="checkbox" name="${esc(name)}" value="${esc(item.id)}"><span>${esc(item.title || item.fileName)}</span></label>`).join('') : `<p class="small">${esc(emptyLabel)}</p>`}</div></fieldset>`;
}

async function openHandoverForm() {
  const teamId = state.team.id;
  const userId = state.user.id;
  const sequence = state.sequence;
  const [members, tasks, resources] = await Promise.all([
    list(`/teams/${enc(teamId)}/members`),
    list(`/teams/${enc(teamId)}/tasks`),
    list('/me/drive/available-resources?scope=all'),
  ]);
  if (sequence !== state.sequence || state.team?.id !== teamId || state.user?.id !== userId) return;
  const recipients = members.filter((member) => member.id !== userId);
  if (!recipients.length) {
    toast('请先邀请其他成员加入课题组，再发起交接', true);
    return;
  }
  openModal(
    '发起资料交接',
    form(
      'handover',
      `<div class="handover-meta">${field('交接标题', 'title', '', { required: true, max: 200 })}${selectField(
        '接收人',
        'toUserId',
        recipients.map((member) => ({ id: member.id, name: member.name })),
      )}</div>` +
        field('交接说明', 'content', '', { textarea: true, rows: 3, required: true, max: 50000 }) +
        '<p class="notice">选择需要记录的任务和资料。资料须先在云盘中共享给接收人，才能确认接收；文件仍归原所有者，任务分工以任务页为准。</p>' +
        `<div class="handover-reference-grid">${referenceOptions('关联任务', 'taskIds', tasks, '当前没有可关联的任务')}${referenceOptions('关联资料', 'resourceIds', resources, '当前没有可关联的资料，请先上传或取得共享权限')}</div>`,
      '发起交接',
      '',
      `data-team-id="${esc(teamId)}"`,
    ),
    '',
    true,
  );
}

async function submitHandover(data, formElement) {
  const teamId = formElement.dataset.teamId;
  if (!state.user || state.team?.id !== teamId) throw new Error('课题组已切换，请重新发起交接');
  const values = new FormData(formElement);
  const taskIds = values.getAll('taskIds');
  const resourceIds = values.getAll('resourceIds');
  if (taskIds.length > 100 || resourceIds.length > 100) {
    throw new Error('关联任务和资料分别最多选择 100 项');
  }
  await api(`/teams/${enc(teamId)}/handovers`, 'POST', {
    title: data.title,
    content: data.content,
    toUserId: data.toUserId,
    taskIds,
    resourceIds,
  });
  closeModal();
  toast('交接已发起');
  await renderPage();
}

async function acceptHandover(id) {
  await api(`/handovers/${enc(id)}/accept`, 'POST', {});
  toast('已接收交接');
  await renderPage();
}

export { renderHandovers, openHandoverForm, submitHandover, acceptHandover };
