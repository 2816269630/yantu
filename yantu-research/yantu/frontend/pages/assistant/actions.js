import { para, tag } from '../../components/ui.js';
import { api } from '../../core/api.js';
import { $, $$ } from '../../core/dom.js';
import { enc, esc } from '../../core/format.js';

async function submitAssistantForm(type, data, id, formElement) {
  let result;
  if (type === 'assistant') {
    const resourceIds = $$('input[name=source]:checked').map((x) => x.value);
    const answer = await api('/me/drive/questions', 'POST', {
      question: data.question,
      resourceIds,
    });
    $('#assistantAnswer').innerHTML =
      `<div class="assistant-response"><div class="between"><strong>${answer.mode === 'generated' ? '资料问答' : '原文检索'}</strong>${tag((answer.sources || []).length + ' 个来源', 'purple')}</div>${para(answer.answer)}${(answer.sources || []).map((s, i) => `<a class="source-cite" href="#resource/${enc(s.resourceId)}"><strong>[${i + 1}] ${esc(s.title)}</strong><span>${esc(s.excerpt)}</span></a>`).join('')}</div>`;
    formElement.reset();
  }
}
export { submitAssistantForm };
