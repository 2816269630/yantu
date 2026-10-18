import { field, modalForm } from '../../components/forms.js';
import { closeModal } from '../../components/modal.js';
import { toast } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { enc } from '../../core/format.js';
import { renderPage } from '../../core/router.js';
import { teamUrl } from '../../core/state.js';

async function handleProgressAction(action, id, source) {
  if (action === 'create-progress' || action === 'create-help')
    return modalForm(
      action === 'create-help' ? '向课题组求助' : '记录研究进展',
      'progress',
      field('记录内容', 'content', '', { textarea: true, required: true }) +
        field('遇到的困难', 'blockers', '', { textarea: true }) +
        field('下一步计划', 'nextPlan', '', { textarea: true }) +
        `<input type="hidden" name="kind" value="${action === 'create-help' ? 'help' : 'progress'}">`,
      '发布',
    );
  if (action === 'comment-progress')
    return modalForm(
      '回复讨论',
      'progress-comment',
      field('回复内容', 'content', '', { textarea: true, required: true }),
      '回复',
      id,
    );
  if (action === 'resolve-progress') {
    await api(`/progress/${enc(id)}`, 'PATCH', { status: 'resolved' });
    toast('已标记为解决');
    return renderPage();
  }
}

async function submitProgressForm(type, data, id, formElement) {
  let result;
  if (type === 'progress') {
    await api(teamUrl('/progress'), 'POST', data);
    closeModal();
    await renderPage();
  }
  if (type === 'progress-comment') {
    await api(`/progress/${enc(id)}/comments`, 'POST', { content: data.content });
    closeModal();
    await renderPage();
  }
}
export { handleProgressAction, submitProgressForm };
