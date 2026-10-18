import { enc } from './format.js';

const roles = { owner: '负责人', mentor: '前辈', student: '学生' };

const statusNames = {
  todo: '待开始',
  doing: '进行中',
  blocked: '遇到困难',
  review: '待反馈',
  done: '已完成',
};

const statusColors = {
  todo: '',
  doing: 'blue',
  blocked: 'orange',
  review: 'purple',
  done: 'green',
};

const typeNames = {
  paper: '论文',
  note: '笔记',
  slides: '组会材料',
  other: '其他',
  tutorial: '教程',
  experience: '经验',
  template: '模板',
};

const scopeNames = { team: '课题组', private: '仅自己', project: '项目成员', public: '公开' };

const state = {
  user: null,
  teams: [],
  team: null,
  system: {},
  page: 'home',
  data: {},
  members: [],
  sequence: 0,
  settingsTab: 'profile',
  filters: {},
  invite: new URLSearchParams(location.search).get('invite') || '',
};

const teamUrl = (suffix) => `/teams/${enc(state.team.id)}${suffix}`;

const isManager = () => ['owner', 'mentor'].includes(state.team?.role);

const isOwner = () => state.team?.role === 'owner';

const pages = {};
export {
  roles,
  statusNames,
  statusColors,
  typeNames,
  scopeNames,
  state,
  teamUrl,
  isManager,
  isOwner,
  pages,
};
