import { api } from '../../core/api.js';
import { enc } from '../../core/format.js';
import { renderPage } from '../../core/router.js';

async function handleHomeAction(action, id, source) {
  if (action === 'read-notification') {
    await api(`/me/notifications/${enc(id)}`, 'PATCH', { read: true });
    return renderPage();
  }
  if (action === 'read-all') {
    await api('/me/notifications/read-all', 'POST', {});
    return renderPage();
  }
}
export { handleHomeAction };
