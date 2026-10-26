import * as Y from 'yjs';

const remote = Symbol('server update');
const encode = bytes => {
  let text = '';
  for (let index = 0; index < bytes.length; index += 0x8000)
    text += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(text);
};
const decode = value => Uint8Array.from(atob(value), character => character.charCodeAt(0));

export function openCollaboration({ id, seed, api, currentContent, onStatus, onPresence, onVersion, onPermissionLost }) {
  let ydoc = null, socket = null, stopped = false, ready = false, editable = false, seeded = false, retries = 0;
  let timer = null, reconnectTimer = null;
  let resolveStart, rejectStart;
  const start = new Promise((resolve, reject) => { resolveStart = resolve; rejectStart = reject; });
  const url = new URL('/api/v1/resources/' + encodeURIComponent(id) + '/collaboration', location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';

  function scheduleSnapshot(delay = 1100) {
    if (!ready || stopped || !editable || !currentContent) return;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!ydoc || !currentContent()) return;
      try {
        const state = encode(Y.encodeStateVector(ydoc));
        const result = await api('/resources/' + encodeURIComponent(id) + '/collaboration/snapshot', 'PUT', {
          state, content: currentContent(),
        });
        if (state === encode(Y.encodeStateVector(ydoc))) {
          onVersion?.(result);
          onStatus?.('已同步到云端');
        } else scheduleSnapshot();
      } catch (error) {
        if (error.status === 409) scheduleSnapshot(1400);
        else if (error.status === 403) { onPermissionLost?.(); onStatus?.('编辑权限已撤销'); }
        else onStatus?.(error.message || '保存失败');
      }
    }, delay);
  }

  function attach(document) {
    if (ready) return;
    ydoc = document;
    ydoc.on('update', (update, origin) => {
      if (origin !== remote && socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'update', update: encode(update) }));
        onStatus?.('同步中…');
      }
      scheduleSnapshot();
    });
    ready = true;
    resolveStart({ document: ydoc, close, scheduleSnapshot, seeded });
    scheduleSnapshot();
  }

  function connect() {
    if (stopped) return;
    socket = new WebSocket(url);
    socket.onopen = () => { retries = 0; onStatus?.('连接协作服务…'); };
    socket.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === 'bootstrap') {
        editable = Boolean(message.canEdit);
        onPresence?.(message.people || []);
        if (message.state) {
          if (ydoc && ready) {
            Y.applyUpdate(ydoc, decode(message.state), remote);
            if (message.canEdit) socket.send(JSON.stringify({ type: 'update', update: encode(Y.encodeStateAsUpdate(ydoc)) }));
          } else {
            seeded = false;
            const document = new Y.Doc();
            Y.applyUpdate(document, decode(message.state), remote);
            attach(document);
          }
        } else if (message.canEdit) {
          seeded = true;
          let initial;
          try { initial = ydoc || seed(); }
          catch (error) {
            stopped = true;
            rejectStart(error);
            socket.close();
            return;
          }
          if (!initial) { stopped = true; rejectStart(new Error('此文档需要先核对格式，暂不能进入实时协作')); socket.close(); return; }
          ydoc = initial;
          socket.send(JSON.stringify({ type: 'seed', update: encode(Y.encodeStateAsUpdate(initial)),
            baseVersion: message.baseVersion }));
        } else {
          stopped = true;
          rejectStart(new Error('文档尚未进入实时协作，请由所有者先打开'));
          socket.close();
        }
      } else if (message.type === 'ack') {
        if (!ready && ydoc) attach(ydoc);
        onStatus?.('已同步到云端');
        scheduleSnapshot();
      } else if (message.type === 'update' && ydoc) {
        Y.applyUpdate(ydoc, decode(message.update), remote);
        scheduleSnapshot();
      } else if (message.type === 'presence') {
        onPresence?.(message.people || []);
      } else if (message.type === 'stale') {
        onStatus?.('文档版本已变化，请刷新');
        if (!ready) { stopped = true; rejectStart(new Error('文档版本已变化，请刷新')); socket.close(); }
      } else if (message.type === 'invalid') {
        onStatus?.('本次修改未能同步，请保留本地内容');
      }
    };
    socket.onerror = () => { if (!ready) onStatus?.('协作连接失败'); };
    socket.onclose = event => {
      if (stopped) return;
      onStatus?.('连接中断，正在重连…');
      if (event.code === 4401 || event.code === 4403) {
        stopped = true;
        onPermissionLost?.();
        if (!ready) rejectStart(new Error('没有文档编辑权限或登录已过期'));
        return;
      }
      if (!ready && retries >= 3) { rejectStart(new Error('无法连接协作服务')); return; }
      retries++;
      reconnectTimer = setTimeout(connect, Math.min(1000 * retries, 5000));
    };
  }

  function close() {
    stopped = true;
    clearTimeout(timer);
    clearTimeout(reconnectTimer);
    socket?.close();
  }
  connect();
  return start;
}
