import { closeModal } from '../components/modal.js';
import { renderPage } from './router.js';
import { boot } from './session.js';

async function handleCommonAction(action, id, source) {
  if (action === 'close') return closeModal();
  if (action === 'boot' || action === 'refresh') return action === 'boot' ? boot() : renderPage();
}
export { handleCommonAction };
