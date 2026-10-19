import { para, tag } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $, $$ } from '../../core/dom.js';
import { enc, esc } from '../../core/format.js';
import { state } from '../../core/state.js';

let interactionsInitialized = false;

function initAssistantInteractions() {
  if (interactionsInitialized) return;
  interactionsInitialized = true;
  const content = $('#content');
  content.addEventListener('input', (event) => {
    if (event.target.id !== 'assistantSourceSearch') return;
    const query = event.target.value.toLocaleLowerCase();
    $$('.source-check', content).forEach((item) => {
      item.hidden = !item.textContent.toLocaleLowerCase().includes(query);
    });
  });
  content.addEventListener('change', (event) => {
    if (!event.target.matches('input[name=source]')) return;
    $('#assistantSelected').textContent =
      `已选择 ${$$('input[name=source]:checked', content).length} 份；本次仅检索勾选资料，空选择检索全部当前有权且可解析的文件`;
  });
}

async function submitAssistantForm(type, data, id, formElement) {
  if (type === 'assistant') {
    const answerBox = $('#assistantAnswer');
    const sequence = state.sequence;
    const resourceIds = $$('input[name=source]:checked').map((x) => x.value);
    const answer = await api('/me/drive/questions', 'POST', {
      question: data.question,
      resourceIds,
    });
    // 切换页面或退出后，旧回答不能写入新的页面。
    if (!answerBox?.isConnected || sequence !== state.sequence) return;
    answerBox.innerHTML = `<div class="assistant-response"><div class="between"><strong>${answer.mode === 'generated' ? '资料问答' : '原文检索'}</strong>${tag((answer.sources || []).length + ' 个来源', 'purple')}</div>${para(answer.answer)}${(answer.sources || []).map((s, i) => `<a class="source-cite" href="#resource/${enc(s.resourceId)}"><strong>[${i + 1}] ${esc(s.title)}</strong><span>${esc(s.excerpt)}</span></a>`).join('')}</div>`;
    formElement.reset();
  }
}
export { initAssistantInteractions, submitAssistantForm };
