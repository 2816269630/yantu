import { icon } from '../../components/icons.js';
import { empty, head, tag } from '../../components/ui.js';
import { esc } from '../../core/format.js';
import { pages, scopeNames, state } from '../../core/state.js';
import { allDriveFiles } from '../drive/browser.js';

pages.assistant = async () => {
  const resources = await allDriveFiles('all');
  state.data.assistantResources = resources;
  return (
    head(
      '科研助手',
      '选择本人云盘或有效共享资料，回答保留原文出处。',
      tag(
        state.system.assistantConfigured ? '资料检索与问答' : '待配置模型',
        state.system.assistantConfigured ? 'purple' : '',
      ),
    ) +
    `<div class="assistant-layout"><aside class="panel sources"><div class="between mb16"><h3>参考资料</h3>${tag(resources.length + ' 份')}</div><p class="small">选择与问题相关的材料；不选择时检索本人及有效共享的可解析文件（最多 100 份）；超过上限请手动选源。PDF、DOCX、TXT、MD 可提取文字。</p><input class="input mt16" id="assistantSourceSearch" aria-label="查找问答资料" placeholder="按名称查找资料"><p class="small mt16" id="assistantSelected">已选择 0 份；空选择检索所有当前有权且可解析的文件</p><div class="source-list mt16">${resources.length ? resources.map((r) => `<label class="source-check"><input type="checkbox" name="source" value="${esc(r.id)}"><span>${esc(r.title)}<small class="sub" style="display:block">${esc(r.owner)} · ${esc(scopeNames[r.visibility] || '课题组')}</small></span></label>`).join('') : '<p class="small">资料库尚为空。先上传资料，再围绕内容提问。</p>'}</div><div class="divider"></div><div class="flex small">${icon('lock')}仅检索有权访问的内容</div></aside><section class="panel chat"><div class="flex">${icon('spark')}<h2>从你当前的卡点开始</h2></div><p class="section-note mt16">描述目标、遇到的现象，以及你已经尝试的办法。回答只作为探索线索，结合原文与前辈反馈继续判断。</p>${!state.system.assistantConfigured ? '<div class="notice mt16">服务端尚未配置问答模型。可以先整理问题或向课题组求助；系统不会生成预设答案。</div>' : ''}<div id="assistantAnswer" aria-live="polite">${empty('把问题说具体一点', '例如：这几份资料对实验设置有哪些要求？', '', 'message')}</div><form class="composer" data-form="assistant"><textarea name="question" aria-label="输入科研问题" placeholder="描述你的目标、卡点和已尝试的方法…" required minlength="2" maxlength="500"></textarea><div class="form-error" role="alert" hidden></div><div class="bottom"><span class="small">答案附有来源，可返回原始资料核对</span><button class="btn primary" type="submit">提问 ${icon('arrow')}</button></div></form></section></div>`
  );
};
