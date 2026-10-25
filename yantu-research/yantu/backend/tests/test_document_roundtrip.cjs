const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/document_v2_roundtrip.json'), 'utf8'));
const { schemaVersion, ...expected } = fixture;
assert.equal(schemaVersion, 2);

const dom = new JSDOM('<!doctype html><div id="first"></div><div id="second"></div>');
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;

(async () => {
  const { Editor } = await import('@tiptap/core');
  const { createDocumentExtensions, documentBlockTypes } = await import('../../frontend/document-schema.mjs');
  const first = new Editor({ element: document.querySelector('#first'), extensions: createDocumentExtensions(), content: fixture });
  first.state.doc.check();
  assert.deepEqual(JSON.parse(JSON.stringify(first.getJSON())), expected, '初次打开必须保留已保存的结构');
  const saved = { schemaVersion: 2, ...first.getJSON() };
  first.destroy();

  const second = new Editor({ element: document.querySelector('#second'), extensions: createDocumentExtensions(), content: saved });
  second.state.doc.check();
  assert.deepEqual(JSON.parse(JSON.stringify(second.getJSON())), expected, '再次打开必须保留节点、属性、标记和块 ID');
  const ids = [];
  const blockTypes = new Set(), inlineTypes = new Set(), marks = new Set();
  second.state.doc.descendants(node => {
    if (documentBlockTypes.includes(node.type.name)) { ids.push(node.attrs.id); blockTypes.add(node.type.name); }
    else inlineTypes.add(node.type.name);
    node.marks.forEach(mark => marks.add(mark.type.name));
  });
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual([...blockTypes].sort(), [...documentBlockTypes].sort(), '每种受支持的块均有往返样本');
  assert.deepEqual([...inlineTypes].sort(), ['hardBreak', 'inlineMath', 'text']);
  assert.deepEqual([...marks].sort(), ['bold', 'code', 'italic', 'link', 'strike', 'underline']);
  second.destroy();
  console.log('文档模型往返契约通过。');
})().catch(error => { console.error(error); process.exitCode = 1; });
