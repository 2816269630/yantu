import { field, memberOptions, modalForm, selectField } from '../../components/forms.js';
import { closeModal } from '../../components/modal.js';
import { api } from '../../core/api.js';
import { $, $$ } from '../../core/dom.js';
import { enc, esc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { state, teamUrl } from '../../core/state.js';
import { taskBoard } from './tasks.js';

async function handleTaskAction(action, id, source) {
  if (action === 'create-task' || action === 'meeting-task') {
    const meetingId = action === 'meeting-task' ? id : '';
    return modalForm(
      '创建科研任务',
      'task',
      field('任务名称', 'title', '', { required: true, max: 200 }) +
        field('任务说明', 'description', '', { textarea: true }) +
        field('完成标准', 'acceptanceCriteria', '', { textarea: true }) +
        selectField('负责人', 'assigneeId', memberOptions()) +
        selectField('反馈人', 'reviewerId', memberOptions('reviewer')) +
        (meetingId ? `<input type="hidden" name="meetingId" value="${esc(meetingId)}">` : ''),
      '创建任务',
    );
  }
  if (action === 'task-progress')
    return modalForm(
      '更新任务进展',
      'task-progress',
      selectField(
        '状态',
        'status',
        [
          { id: 'todo', name: '待开始' },
          { id: 'doing', name: '进行中' },
          { id: 'blocked', name: '遇到困难' },
        ],
        state.data.task?.status || 'doing',
      ) + field('卡点记录', 'blocker', state.data.task?.blocker || '', { textarea: true }),
      '保存',
      id,
    );
  if (action === 'submit-task')
    return modalForm(
      '提交任务产出',
      'submission',
      field('产出说明', 'summary', '', { textarea: true, required: true }) +
        field('成果链接（可选）', 'url', '', { type: 'url' }),
      '提交反馈',
      id,
    );
  if (action === 'review-submission')
    return modalForm(
      '提交审核反馈',
      'review',
      selectField('审核结果', 'decision', [
        { id: 'approved', name: '确认完成' },
        { id: 'changes_requested', name: '继续完善' },
      ]) + field('反馈内容', 'comment', '', { textarea: true, required: true }),
      '提交反馈',
      id,
    );
  if (action === 'task-tab') {
    history.replaceState(null, '', '#tasks/' + (id === 'review' ? 'review' : 'mine'));
    const items = id === 'review' ? state.data.reviews : state.data.tasks;
    $('#taskBoard').innerHTML = taskBoard(items);
    $$('.tabs .tab').forEach((x) => x.classList.toggle('active', x.dataset.id === id));
    return;
  }
}

async function submitTaskForm(type, data, id, formElement) {
  let result;
  if (type === 'task') {
    result = await api(teamUrl('/tasks'), 'POST', data);
    closeModal();
    navigate('task/' + result.id);
  }
  if (type === 'task-progress') {
    await api(`/tasks/${enc(id)}`, 'PATCH', { status: data.status, blocker: data.blocker });
    closeModal();
    await renderPage();
  }
  if (type === 'submission') {
    await api(`/tasks/${enc(id)}/submissions`, 'POST', data);
    closeModal();
    await renderPage();
  }
  if (type === 'review') {
    await api(`/submissions/${enc(id)}/reviews`, 'POST', data);
    closeModal();
    await renderPage();
  }
}
export { handleTaskAction, submitTaskForm };
