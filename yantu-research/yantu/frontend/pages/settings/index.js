import { field, form } from '../../components/forms.js';
import { icon } from '../../components/icons.js';
import { avatar, btn, empty, head, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { datetime, esc } from '../../core/format.js';
import { isOwner, pages, roles, state, teamUrl } from '../../core/state.js';

pages.settings = async () => {
  const tabs = [
    ['profile', '个人资料'],
    ['team', '课题组'],
    ['members', '成员与邀请'],
    ['handover', '资料交接'],
    ['export', '导出与备份'],
  ];
  if (!state.team && !['profile', 'team'].includes(state.settingsTab)) state.settingsTab = 'team';
  const content = await settingsContent(state.settingsTab);
  return (
    head('空间与权限', '让个人探索、组内共享与经验交接各有边界。') +
    `<div class="settings-menu">${tabs
      .filter(([k]) => state.team || ['profile', 'team'].includes(k))
      .map(([k, v]) => btn(v, 'settings-tab', k, state.settingsTab === k ? 'soft' : ''))
      .join('')}</div><div class="settings-content">${content}</div>`
  );
};

async function settingsContent(tab) {
  if (tab === 'profile')
    return `<div class="settings-grid"><section class="panel padded"><h2 class="mb16">个人资料</h2>${form('profile', field('显示名称', 'displayName', state.user.displayName, { required: true, max: 100 }) + field('研究方向', 'direction', state.user.direction, { max: 255 }) + `<p class="small">登录邮箱：${esc(state.user.email)}</p>`, '保存个人信息')}</section><section class="panel padded"><h2>当前身份</h2><div class="flex mt16">${avatar(state.user.displayName, 'large')}<div><h3>${esc(state.user.displayName)}</h3><p class="small">${esc(state.team?.name || '尚未加入课题组')} · ${esc(roles[state.team?.role] || '科研成员')}</p></div></div><div class="divider"></div><p class="section-note">角色属于当前课题组。不同课题组中的成员资格与内容权限分别管理。</p>${btn(icon('logout') + '退出登录', 'logout', '', 'mt16')}</section></div>`;
  if (tab === 'team') {
    const team = state.team ? await api(teamUrl('')) : null;
    state.data.team = team;
    return `<div class="settings-grid"><section class="panel padded"><h2 class="mb16">${team ? '课题组信息' : '创建科研空间'}</h2>${team ? (isOwner() ? form('team', field('课题组名称', 'name', team.name, { required: true, max: 100 }) + field('空间介绍', 'description', team.description, { textarea: true }), '保存修改') : `<h3>${esc(team.name)}</h3><div class="rich-section">${para(team.description || '暂无空间介绍')}</div>`) : empty('建立你的第一个课题组', '创建者将成为负责人，可以邀请成员并维护空间。', btn('创建课题组', 'create-team', '', 'primary'), 'people')}</section><section class="panel padded"><h2>管理我的空间</h2><p class="section-note mt16">通过左侧选择器切换已加入的课题组，每个空间的数据与权限独立管理。</p><div class="section-actions mt16">${btn(icon('plus') + '新建课题组', 'create-team')}${btn('接受邀请', 'accept-invite')}</div></section></div>`;
  }
  if (tab === 'members') {
    const members = await list(teamUrl('/members'));
    state.members = members;
    const invites = isOwner() ? await list(teamUrl('/invitations')) : [];
    return `<div class="stack"><section class="panel"><div class="panelhead"><h2>课题组成员 ${tag(members.length)}</h2>${isOwner() ? btn(icon('plus') + '邀请成员', 'invite-member', '', 'primary') : ''}</div>${members.map((m) => `<div class="row member-row">${avatar(m.name, m.role === 'mentor' ? 'mint' : '')}<div class="row-main"><h3>${esc(m.name)}${m.id === state.user.id ? ' · 我' : ''}</h3><p>${esc(m.email || { owner: '管理空间与成员', mentor: '维护路线与反馈任务', student: '学习、提交产出与提问' }[m.role])}</p></div>${tag(roles[m.role], m.role === 'owner' ? 'blue' : '')}${isOwner() && m.role !== 'owner' ? `${btn('调整角色', 'member-role', m.id, 'sm')}${btn('移出', 'remove-member', m.id, 'sm danger-text')}` : ''}</div>`).join('')}</section>${isOwner() ? `<section class="panel"><div class="panelhead"><h2>邀请记录</h2><span class="small">邀请链接由负责人自行分享</span></div>${invites.length ? invites.map((i) => `<div class="row"><div class="row-main"><h3>${esc(i.email)}</h3><p>${esc(roles[i.role])} · 有效至 ${i.expiresAt ? datetime(i.expiresAt) : '未指定'}</p></div>${tag(i.status === 'accepted' || i.acceptedAt ? '已接受' : i.status === 'expired' ? '已过期' : '待接受', i.status === 'accepted' || i.acceptedAt ? 'green' : 'orange')}</div>`).join('') : empty('暂无待处理邀请', '邀请学生与前辈，一起维护科研空间。', '', 'people')}</section>` : ''}</div>`;
  }
  if (tab === 'handover') {
    const items = await list(teamUrl('/handovers'));
    state.data.handovers = items;
    return `<section class="panel"><div class="panelhead"><h2>毕业与资料交接</h2>${btn(icon('plus') + '发起交接', 'create-handover', '', 'primary')}</div>${items.length ? items.map((h) => `<article class="padded" style="border-bottom:1px solid var(--line)"><div class="between mb16"><h3>${esc(h.title)}</h3>${tag(h.status === 'accepted' || h.acceptedAt ? '已接收' : '待接收', h.status === 'accepted' || h.acceptedAt ? 'green' : 'orange')}</div><p class="small mb16">${esc(h.fromUserName || h.fromName || h.author || '交接人')} → ${esc(h.toUserName || h.toName || '接收人')} · ${datetime(h.createdAt)}</p>${para(h.content)}<p class="small mt16">${(h.taskIds || []).length} 项任务 · ${(h.resourceIds || []).length} 份资料</p>${h.toUserId === state.user.id && !h.acceptedAt && h.status !== 'accepted' ? `<div class="form-actions">${btn('确认接收交接', 'accept-handover', h.id, 'primary')}</div>` : ''}</article>`).join('') : empty('让研究在交接后继续', '保留未解决问题、资料使用条件与下一步，指定新的维护人。', btn('发起第一次交接', 'create-handover', '', 'primary'), 'history')}</section>`;
  }
  return `<div class="settings-grid"><section class="panel padded"><h2>导出课题组记录</h2><p class="section-note mt16">下载你有权限读取的科研记录，包括学习路线、任务、组会和资料清单。导出为结构化 JSON，便于归档或进一步处理。</p>${btn(icon('download') + '导出科研记录', 'export', '', 'primary mt16')}<p class="helptext mt16">原始附件请从资料详情页下载。导出内容遵守当前账号的访问权限。</p></section><section class="panel padded"><h2>本地数据备份</h2><p class="section-note mt16">完整恢复需要同时保留科研数据库和上传文件。此处导出用于阅读与归档；系统管理员可使用部署目录中的备份说明执行完整备份。</p><div class="divider"></div><div class="flex small">${icon('lock')}你正在使用本地部署的科研空间</div></section></div>`;
}
export { settingsContent };
