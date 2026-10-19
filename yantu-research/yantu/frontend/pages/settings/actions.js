import { field, modalForm, selectField } from '../../components/forms.js';
import { closeModal, openModal } from '../../components/modal.js';
import { toast } from '../../components/ui.js';
import { api, download } from '../../core/api.js';
import { enc, esc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { refreshTeams } from '../../core/session.js';
import { state, teamUrl } from '../../core/state.js';
import { acceptHandover, openHandoverForm, submitHandover } from './handovers.js';

async function handleSettingsAction(action, id, source) {
  if (action === 'settings-tab') {
    state.settingsTab = id;
    return renderPage();
  }
  if (action === 'create-team')
    return modalForm(
      '创建课题组',
      'create-team',
      field('课题组名称', 'name', '', { required: true, max: 100 }) +
        field('空间介绍', 'description', '', { textarea: true }),
      '创建',
    );
  if (action === 'accept-invite')
    return modalForm(
      '接受课题组邀请',
      'accept-invite',
      field('邀请令牌', 'token', '', { required: true }),
      '加入课题组',
    );
  if (action === 'invite-member')
    return modalForm(
      '邀请成员',
      'invite-member',
      field('邮箱', 'email', '', { type: 'email', required: true }) +
        selectField('角色', 'role', [
          { id: 'student', name: '学生' },
          { id: 'mentor', name: '前辈' },
        ]),
      '生成邀请链接',
    );
  if (action === 'export') return download(teamUrl('/export'), '研途课题组导出.json');
  if (action === 'accept-handover') return acceptHandover(id);
  if (action === 'create-handover') return openHandoverForm();
  if (action === 'member-role') {
    const m = state.members.find((x) => x.id === id);
    return modalForm(
      '调整成员角色',
      'member-role',
      selectField(
        '角色',
        'role',
        [
          { id: 'student', name: '学生' },
          { id: 'mentor', name: '前辈' },
        ],
        m.role,
      ),
      '保存',
      id,
    );
  }
  if (action === 'remove-member') {
    await api(teamUrl(`/members/${enc(id)}`), 'DELETE');
    toast('成员已移出');
    return renderPage();
  }
  if (action === 'open-team-settings') {
    state.settingsTab = 'team';
    return navigate('settings');
  }
}

async function submitSettingsForm(type, data, id, formElement) {
  let result;
  if (type === 'create-team') {
    result = await api('/teams', 'POST', data);
    await refreshTeams(result.id);
    closeModal();
    await renderPage();
  }
  if (type === 'accept-invite') {
    result = await api(`/invitations/${enc(data.token)}/accept`, 'POST', {});
    await refreshTeams(result.teamId);
    closeModal();
    await renderPage();
  }
  if (type === 'invite-member') {
    result = await api(teamUrl('/invitations'), 'POST', data);
    closeModal();
    openModal(
      '邀请已创建',
      `<p>请把下面的链接发给受邀成员：</p><div class="notice body-text">${esc(result.inviteUrl)}</div>`,
    );
  }
  if (type === 'handover') {
    return submitHandover(data, formElement);
  }
  if (type === 'member-role') {
    await api(teamUrl(`/members/${enc(id)}`), 'PATCH', data);
    closeModal();
    await refreshTeams(state.team.id);
    await renderPage();
  }
  if (type === 'profile') {
    state.user = await api('/me', 'PATCH', data);
    await renderPage();
    toast('个人资料已保存');
  }
  if (type === 'team') {
    await api(teamUrl(''), 'PATCH', data);
    await refreshTeams(state.team.id);
    await renderPage();
    toast('课题组信息已保存');
  }
}
export { handleSettingsAction, submitSettingsForm };
