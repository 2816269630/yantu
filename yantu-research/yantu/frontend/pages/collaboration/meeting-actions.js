import { field, modalForm } from '../../components/forms.js';
import { closeModal } from '../../components/modal.js';
import { toast } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { enc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { state, teamUrl } from '../../core/state.js';
import { meetingCards } from './meetings.js';

async function handleMeetingAction(action, id, source) {
  if (action === 'create-meeting')
    return modalForm(
      '新建组会',
      'meeting',
      field('组会主题', 'title', '', { required: true, max: 200 }) +
        field('开始时间', 'startsAt', '', { type: 'datetime-local', required: true }) +
        field('地点或会议链接', 'location', '', { required: true }) +
        field('讨论议程', 'agenda', '', { textarea: true, required: true }),
      '创建组会',
    );
  if (action === 'edit-meeting') {
    const m = state.data.meeting;
    const local = new Date(m.startsAt);
    local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
    return modalForm(
      '编辑组会',
      'edit-meeting',
      field('组会主题', 'title', m.title, { required: true }) +
        field('开始时间', 'startsAt', local.toISOString().slice(0, 16), {
          type: 'datetime-local',
          required: true,
        }) +
        field('地点或会议链接', 'location', m.location, { required: true }) +
        field('讨论议程', 'agenda', m.agenda, { textarea: true, required: true }),
      '保存',
      id,
    );
  }
  if (action === 'meeting-minutes')
    return modalForm(
      '记录组会纪要',
      'minutes',
      field('纪要内容', 'content', state.data.meeting?.minutes?.content || '', {
        textarea: true,
        required: true,
        rows: 8,
      }),
      '保存纪要',
      id,
    );
  if (action === 'meeting-question')
    return modalForm(
      '补充讨论问题',
      'meeting-question',
      field('具体问题', 'content', '', { textarea: true, required: true }),
      '添加问题',
      id,
    );
  if (action === 'answer-meeting-question')
    return modalForm(
      '记录讨论回应',
      'meeting-answer',
      field('回应内容', 'answer', '', { textarea: true, required: true }),
      '标记已回应',
      id,
    );
  if (action === 'meeting-complete' || action === 'meeting-archive') {
    await api(`/meetings/${enc(id)}`, 'PATCH', {
      status: action === 'meeting-complete' ? 'completed' : 'archived',
    });
    toast('组会状态已更新');
    return renderPage();
  }
  if (action === 'meeting-filter') {
    const items =
      id === 'all'
        ? state.data.meetings
        : state.data.meetings.filter((m) => (m.status || 'scheduled') === id);
    $('#meetingCards').innerHTML = meetingCards(items);
    return;
  }
}

async function submitMeetingForm(type, data, id, formElement) {
  let result;
  if (type === 'meeting') {
    data.startsAt = new Date(data.startsAt).toISOString();
    result = await api(teamUrl('/meetings'), 'POST', data);
    closeModal();
    navigate('meeting/' + result.id);
  }
  if (type === 'edit-meeting') {
    data.startsAt = new Date(data.startsAt).toISOString();
    await api(`/meetings/${enc(id)}`, 'PATCH', data);
    closeModal();
    await renderPage();
  }
  if (type === 'minutes') {
    await api(`/meetings/${enc(id)}/minutes`, 'PUT', { content: data.content });
    closeModal();
    await renderPage();
  }
  if (type === 'meeting-question') {
    await api(`/meetings/${enc(id)}/questions`, 'POST', { content: data.content });
    closeModal();
    await renderPage();
  }
  if (type === 'meeting-answer') {
    await api(`/meeting-questions/${enc(id)}`, 'PATCH', {
      answer: data.answer,
      status: 'resolved',
    });
    closeModal();
    await renderPage();
  }
}
export { handleMeetingAction, submitMeetingForm };
