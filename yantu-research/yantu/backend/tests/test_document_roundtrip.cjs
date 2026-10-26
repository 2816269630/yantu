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
  assert.deepEqual([...blockTypes].sort(), documentBlockTypes.filter(type => !['imageResource', 'fileResource'].includes(type)).sort(), '旧版块的往返样本保持一致');
  assert.deepEqual([...inlineTypes].sort(), ['hardBreak', 'inlineMath', 'text']);
  assert.deepEqual([...marks].sort(), ['bold', 'code', 'italic', 'link', 'strike', 'underline']);
  second.destroy();
  const assets = { schemaVersion: 2, type: 'doc', content: [
    { type: 'imageResource', attrs: { id: '00000000-0000-4000-8000-000000000031', resourceId: '00000000-0000-4000-8000-000000000041', name: '图像.png' } },
    { type: 'fileResource', attrs: { id: '00000000-0000-4000-8000-000000000032', resourceId: '00000000-0000-4000-8000-000000000042', name: '附件.pdf' } },
    { type: 'paragraph', attrs: { id: '00000000-0000-4000-8000-000000000033' }, content: [
      { type: 'text', text: '参见 ' },
      { type: 'documentReference', attrs: { resourceId: '00000000-0000-4000-8000-000000000043' } },
      { type: 'text', text: ' 的结果' },
    ] },
  ] };
  const assetEditor = new Editor({ element: document.querySelector('#first'), extensions: createDocumentExtensions({
    documentId: '00000000-0000-4000-8000-000000000050', resolveReference: async () => '被引用文档',
  }), content: assets });
  assetEditor.state.doc.check();
  assert.deepEqual(JSON.parse(JSON.stringify({ schemaVersion: 2, ...assetEditor.getJSON() })), assets, '图片与附件节点再次打开保持资源 ID 与名称');
  assert.ok(assetEditor.view.dom.querySelector('img[src*="/assets/"]'), '图片指向文档授权的资源地址');
  assert.ok(assetEditor.view.dom.querySelector('a[href*="/assets/"]'), '附件指向文档授权的下载地址');
  await Promise.resolve();
  assert.equal(assetEditor.view.dom.querySelector('[data-document-reference] a').textContent, '▤ 被引用文档');
  assert.ok(assetEditor.view.dom.querySelector('[data-document-reference] a[href*="#resource/"]'), '文档引用保留资源身份和独立打开路径');
  assetEditor.destroy();
  const unavailableEditor = new Editor({ element: document.querySelector('#second'), extensions: createDocumentExtensions({
    resolveReference: async () => null,
  }), content: assets });
  await Promise.resolve();
  const unavailableLink = unavailableEditor.view.dom.querySelector('[data-document-reference] a');
  assert.equal(unavailableLink.textContent, '▤ 文档不可用');
  assert.equal(unavailableLink.hasAttribute('href'), false, '无权访问时不提供目标跳转');
  unavailableEditor.destroy();
  console.log('文档模型往返契约通过。');
})().catch(error => { console.error(error); process.exitCode = 1; });
