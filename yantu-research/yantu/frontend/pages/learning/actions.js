import { field, memberOptions, modalForm, selectField } from '../../components/forms.js';
import { closeModal, openModal } from '../../components/modal.js';
import { toast } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { datetime, enc, esc } from '../../core/format.js';
import { navigate, renderPage } from '../../core/router.js';
import { state, teamUrl } from '../../core/state.js';
import { experienceCards } from './experiences.js';
import { routeCards } from './routes.js';

async function handleLearningAction(action, id, source) {
  if (action === 'create-route')
    return modalForm(
      '创建学习路线',
      'route',
      field('路线名称', 'title', '', { required: true, max: 200 }) +
        field('路线说明', 'description', '', { textarea: true }) +
        field('研究方向', 'direction', '', { max: 255 }) +
        field('建议基础', 'difficulty', '入门', { max: 60 }) +
        field('阶段名称', 'stageTitle', '', { required: true, max: 200 }) +
        field('阶段目标', 'stageDescription', '', { textarea: true }) +
        field('第一个任务', 'taskTitle', '', { max: 200 }) +
        field('完成标准', 'acceptanceCriteria', '', { textarea: true }),
      '创建路线',
    );
  if (action === 'edit-route') {
    const r = state.data.route;
    return modalForm(
      '编辑学习路线',
      'edit-route',
      field('路线名称', 'title', r.title, { required: true, max: 200 }) +
        field('路线说明', 'description', r.description, { textarea: true }) +
        field('研究方向', 'direction', r.direction) +
        field('建议基础', 'difficulty', r.difficulty),
      '保存新版本',
      id,
    );
  }
  if (action === 'route-versions') {
    const rows = await list(`/routes/${enc(id)}/versions`);
    return openModal(
      '路线版本记录',
      rows.length
        ? rows
            .map(
              (v) =>
                `<div class="version-item"><strong>版本 ${esc(v.version)}</strong><p class="small">${datetime(v.createdAt)}</p></div>`,
            )
            .join('')
        : '<p>暂无版本记录</p>',
    );
  }
  if (action === 'enroll') {
    const result = await api(`/routes/${enc(id)}/enrollments`, 'POST', {});
    toast('已加入学习计划');
    navigate('plan/' + result.id);
    return;
  }
  if (action === 'adjust-plan') {
    const p = state.data.plan;
    return modalForm(
      '调整学习计划',
      'adjust-plan',
      selectField(
        '计划状态',
        'status',
        [
          { id: 'active', name: '学习中' },
          { id: 'paused', name: '暂停' },
        ],
        p.status,
      ) +
        field('个人调整说明', 'note', p.note || '', { textarea: true }) +
        field('目标日期', 'targetDate', p.targetDate?.slice(0, 10) || '', { type: 'date' }),
      '保存计划',
      id,
    );
  }
  if (action === 'plan-task')
    return modalForm(
      '补充学习任务',
      'plan-task',
      field('任务名称', 'title', '', { required: true }) +
        field('任务说明', 'description', '', { textarea: true }) +
        field('完成标准', 'acceptanceCriteria', '', { textarea: true }) +
        selectField('反馈人', 'reviewerId', memberOptions('reviewer')),
      '创建任务',
      id,
    );
  if (action === 'create-experience')
    return modalForm(
      '分享科研经历',
      'experience',
      field('标题', 'title', '', { required: true, max: 100 }) +
        field('我当时的起点', 'startingPoint', '', { textarea: true, required: true }) +
        field('经历、调整与建议', 'content', '', { textarea: true, required: true }) +
        field('标签（逗号分隔）', 'tags', ''),
      '发布',
    );
  if (action === 'edit-experience') {
    const e = state.data.experience;
    return modalForm(
      '编辑科研经历',
      'edit-experience',
      field('标题', 'title', e.title, { required: true }) +
        field('我当时的起点', 'startingPoint', e.startingPoint, {
          textarea: true,
          required: true,
        }) +
        field('经历、调整与建议', 'content', e.content, { textarea: true, required: true }) +
        field('标签（逗号分隔）', 'tags', (e.tags || []).join(',')),
      '保存',
      id,
    );
  }
  if (action === 'bookmark' || action === 'unbookmark') {
    await api(
      `/experiences/${enc(id)}/bookmark`,
      action === 'bookmark' ? 'PUT' : 'DELETE',
      action === 'bookmark' ? {} : undefined,
    );
    toast(action === 'bookmark' ? '已收藏' : '已取消收藏');
    return renderPage();
  }
  if (action === 'experience-filter') {
    const items =
      id === 'bookmarked'
        ? state.data.experiences.filter((e) => state.data.bookmarks.has(e.id))
        : state.data.experiences;
    $('#experienceCards').innerHTML = experienceCards(items);
    return;
  }
  if (action === 'route-filter') {
    const items = id === 'mine' ? state.data.routes.filter((r) => r.enrolled) : state.data.routes;
    $('#routeCards').innerHTML = routeCards(items);
    return;
  }
}

async function submitLearningForm(type, data, id, formElement) {
  let result;
  if (type === 'route') {
    const tasks = data.taskTitle
      ? [{ title: data.taskTitle, acceptanceCriteria: data.acceptanceCriteria || '' }]
      : [];
    result = await api(teamUrl('/routes'), 'POST', {
      title: data.title,
      description: data.description,
      direction: data.direction,
      difficulty: data.difficulty,
      stages: [
        { title: data.stageTitle, description: data.stageDescription, tasks, resources: [] },
      ],
    });
    closeModal();
    navigate('route/' + result.id);
  }
  if (type === 'edit-route') {
    const r = state.data.route;
    await api(`/routes/${enc(id)}`, 'PATCH', { ...data, stages: r.stages, tags: r.tags || [] });
    closeModal();
    await renderPage();
  }
  if (type === 'adjust-plan') {
    await api(`/enrollments/${enc(id)}`, 'PATCH', data);
    closeModal();
    await renderPage();
  }
  if (type === 'plan-task') {
    await api(`/enrollments/${enc(id)}/tasks`, 'POST', data);
    closeModal();
    await renderPage();
  }
  if (type === 'experience') {
    data.tags = data.tags
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    result = await api(teamUrl('/experiences'), 'POST', data);
    closeModal();
    navigate('experience/' + result.id);
  }
  if (type === 'edit-experience') {
    data.tags = data.tags
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    await api(`/experiences/${enc(id)}`, 'PATCH', data);
    closeModal();
    await renderPage();
  }
}
export { handleLearningAction, submitLearningForm };
