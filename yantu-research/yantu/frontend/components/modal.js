import { loading } from './ui.js';
import { $ } from '../core/dom.js';
import { esc } from '../core/format.js';
import { state } from '../core/state.js';

function openModal(title, content, foot = '', wide = false) {
  state.returnFocus = document.activeElement;
  $('#modal').classList.toggle('dialog-wide', wide);
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = content;
  $('#modalFoot').innerHTML = foot;
  $('#modalFoot').hidden = !foot;
  if (!$('#modal').open) $('#modal').showModal();
}

function closeModal() {
  $('#modal').close();
  if (state.returnFocus?.isConnected) state.returnFocus.focus();
}

async function modalLoad(title, callback, wide = false) {
  openModal(title, loading(), '', wide);
  try {
    const html = await callback();
    if ($('#modal').open) $('#modalBody').innerHTML = html;
  } catch (e) {
    if ($('#modal').open)
      $('#modalBody').innerHTML = `<div class="errorbox">${esc(e.message)}</div>`;
  }
}
export { openModal, closeModal, modalLoad };
