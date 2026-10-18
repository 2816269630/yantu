import { openModal } from './modal.js';
import { btn, toast } from './ui.js';
import { $ } from '../core/dom.js';
import { esc } from '../core/format.js';
import { roles, state } from '../core/state.js';

const field = (label, name, value = '', options = {}) =>
  `<div class="field ${options.full ? 'full' : ''}"><label for="f-${esc(name)}">${esc(label)}${options.required ? ' <span aria-hidden="true">*</span>' : ''}</label>${options.textarea ? `<textarea class="input" id="f-${esc(name)}" name="${esc(name)}" rows="${options.rows || 4}" ${options.required ? 'required' : ''} ${options.max ? `maxlength="${options.max}"` : ''}>${esc(value)}</textarea>` : `<input class="input" id="f-${esc(name)}" name="${esc(name)}" type="${options.type || 'text'}" value="${esc(value)}" ${options.required ? 'required' : ''} ${options.min ? `minlength="${options.min}"` : ''} ${options.max ? `maxlength="${options.max}"` : ''} ${options.placeholder ? `placeholder="${esc(options.placeholder)}"` : ''} ${options.autocomplete ? `autocomplete="${options.autocomplete}"` : ''}>`}${options.help ? `<span class="helptext">${esc(options.help)}</span>` : ''}</div>`;

const selectField = (label, name, items, current = '', optional = false) =>
  `<div class="field"><label for="f-${esc(name)}">${esc(label)}</label><select class="input" id="f-${esc(name)}" name="${esc(name)}" ${optional ? '' : 'required'}>${optional ? '<option value="">不关联</option>' : ''}${items.map((v) => `<option value="${esc(v.id ?? v.value)}" ${String(v.id ?? v.value) === String(current) ? 'selected' : ''}>${esc(v.name ?? v.title ?? v.label)}</option>`).join('')}</select></div>`;

const form = (type, contents, submit = '保存', id = '', extra = '') =>
  `<form class="form-stack" data-form="${esc(type)}" data-id="${esc(id)}" ${extra}>${contents}<div class="form-error" role="alert" hidden></div><div class="form-actions">${btn('取消', 'close')}<button class="btn primary" type="submit">${esc(submit)}</button></div></form>`;

function values(formElement) {
  return Object.fromEntries(new FormData(formElement).entries());
}

function memberOptions(role) {
  return state.members
    .filter(
      (m) =>
        !role || m.role === role || (role === 'reviewer' && ['mentor', 'owner'].includes(m.role)),
    )
    .map((m) => ({ id: m.id, name: `${m.name} · ${roles[m.role]}` }));
}

function modalForm(title, type, contents, submit = '保存', id = '') {
  openModal(title, form(type, contents, submit, id));
}

function showFormError(formElement, error) {
  const box = $('.form-error', formElement);
  if (box) {
    box.textContent = error.message;
    box.hidden = false;
  }
  toast(error.message, true);
}
export { field, selectField, form, values, memberOptions, modalForm, showFormError };
