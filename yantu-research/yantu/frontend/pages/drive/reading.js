import { api } from '../../core/api.js';
import { $ } from '../../core/dom.js';
import { enc } from '../../core/format.js';
import { registerSessionCleanup } from '../../core/session-state.js';
import { state } from '../../core/state.js';

let readingSaveTimer;

registerSessionCleanup(() => {
  clearTimeout(readingSaveTimer);
  readingSaveTimer = undefined;
});

function saveReadingProgress(resourceId, values) {
  clearTimeout(readingSaveTimer);
  const userId = state.user?.id;
  if (!userId) return;
  readingSaveTimer = setTimeout(() => {
    if (state.user?.id !== userId) return;
    api(`/resources/${enc(resourceId)}/reading-progress`, 'PATCH', values).catch(() => {});
  }, 500);
}

function initReadingProgress() {
  const r = state.data.resource;
  if (!r || state.page !== 'resource') return;
  const progress = r.readingProgress || {},
    scroll = $('[data-reading-scroll]'),
    frame = $('[data-reading-frame]'),
    media = $('[data-reading-media]');
  if (scroll) {
    requestAnimationFrame(() => {
      scroll.scrollTop =
        (progress.ratio || 0) * Math.max(0, scroll.scrollHeight - scroll.clientHeight);
    });
    scroll.addEventListener('scroll', () =>
      saveReadingProgress(r.id, {
        ratio: scroll.scrollTop / Math.max(1, scroll.scrollHeight - scroll.clientHeight),
      }),
    );
  }
  if (frame)
    frame.addEventListener('load', () => {
      try {
        const root =
          frame.contentDocument.scrollingElement || frame.contentDocument.documentElement;
        root.scrollTop = (progress.ratio || 0) * Math.max(0, root.scrollHeight - root.clientHeight);
        frame.contentWindow.addEventListener('scroll', () =>
          saveReadingProgress(r.id, {
            ratio: root.scrollTop / Math.max(1, root.scrollHeight - root.clientHeight),
          }),
        );
      } catch (_) {}
    });
  if (media) {
    media.addEventListener(
      'loadedmetadata',
      () => {
        if (progress.time && progress.time < media.duration) media.currentTime = progress.time;
      },
      { once: true },
    );
    media.addEventListener('timeupdate', () =>
      saveReadingProgress(r.id, { time: media.currentTime }),
    );
  }
}
export { readingSaveTimer, saveReadingProgress, initReadingProgress };
