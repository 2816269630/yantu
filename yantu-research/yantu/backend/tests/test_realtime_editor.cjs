const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<div id="a"></div><div id="b"></div>');
global.window = dom.window;
global.document = dom.window.document;

(async () => {
  const Y = await import('yjs');
  const { Editor } = await import('@tiptap/core');
  const { prosemirrorJSONToYDoc } = await import('y-prosemirror');
  const { createDocumentExtensions } = await import('../../frontend/document-schema.mjs');
  const initial = { type: 'doc', content: [{ type: 'paragraph',
    attrs: { id: '00000000-0000-4000-8000-000000000001' },
    content: [{ type: 'text', text: '起点' }] }] };
  const source = new Editor({ extensions: createDocumentExtensions(), content: initial });
  const leftDoc = prosemirrorJSONToYDoc(source.schema, source.getJSON());
  source.destroy();
  const rightDoc = new Y.Doc();
  Y.applyUpdate(rightDoc, Y.encodeStateAsUpdate(leftDoc));
  const left = new Editor({ element: document.querySelector('#a'),
    extensions: createDocumentExtensions({ collaboration: leftDoc }) });
  const right = new Editor({ element: document.querySelector('#b'),
    extensions: createDocumentExtensions({ collaboration: rightDoc }) });
  left.commands.insertContentAt(3, '甲');
  right.commands.insertContentAt(3, '乙');
  Y.applyUpdate(leftDoc, Y.encodeStateAsUpdate(rightDoc));
  Y.applyUpdate(rightDoc, Y.encodeStateAsUpdate(leftDoc));
  assert.equal(left.getText(), right.getText(), '两个编辑器应收敛到相同内容');
  assert.ok(left.getText().includes('甲') && left.getText().includes('乙'));
  const reopenedDoc = new Y.Doc();
  Y.applyUpdate(reopenedDoc, Y.encodeStateAsUpdate(leftDoc));
  const reopened = new Editor({ extensions: createDocumentExtensions({ collaboration: reopenedDoc }) });
  assert.equal(reopened.getText(), left.getText(), '刷新后从持久化更新恢复内容');
  left.destroy(); right.destroy(); reopened.destroy();
  leftDoc.destroy(); rightDoc.destroy(); reopenedDoc.destroy();
  console.log('多人编辑器同步与重开验收通过。');
})().catch(error => { console.error(error); process.exitCode = 1; });
