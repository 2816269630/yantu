import StarterKit from '@tiptap/starter-kit';
import { Mathematics } from '@tiptap/extension-mathematics';
import { TableKit, TableCell, TableHeader } from '@tiptap/extension-table';
import { UniqueID } from '@tiptap/extension-unique-id';
import { Markdown } from '@tiptap/markdown';
import { Node } from '@tiptap/core';
import Collaboration from '@tiptap/extension-collaboration';

export const documentBlockTypes = [
  'paragraph', 'heading', 'bulletList', 'orderedList', 'listItem',
  'blockquote', 'codeBlock', 'horizontalRule', 'blockMath',
  'table', 'tableRow', 'tableCell', 'tableHeader', 'imageResource', 'fileResource',
];

const asset = (name, tag) => Node.create({
  name, group: 'block', atom: true, selectable: true, draggable: true,
  addOptions() { return { documentId: '' }; },
  addAttributes() { return { id: { default: null }, resourceId: { default: null }, name: { default: '' } }; },
  parseHTML() { return [{ tag: `${tag}[data-resource-id]`, getAttrs: element => ({
    id: element.getAttribute('data-block-id'), resourceId: element.getAttribute('data-resource-id'),
    name: element.getAttribute('data-name') || '',
  }) }]; },
  renderHTML({ node }) {
    const { id, resourceId, name: label } = node.attrs;
    const path = this.options.documentId
      ? `/api/v1/resources/${encodeURIComponent(this.options.documentId)}/assets/${encodeURIComponent(resourceId)}`
      : `/api/v1/resources/${encodeURIComponent(resourceId)}`;
    const attributes = { 'data-block-id': id, 'data-resource-id': resourceId, 'data-name': label,
      'data-document-asset': name === 'imageResource' ? 'image' : 'file' };
    return name === 'imageResource'
      ? ['figure', attributes, ['img', { src: `${path}/preview`, alt: label, loading: 'lazy' }], ['figcaption', {}, ['a', { href: `${path}/download`, download: label }, label]]]
      : ['div', attributes, ['a', { href: `${path}/download`, download: label }, '▤  ', label]];
  },
});
const ImageResource = asset('imageResource', 'figure');
const FileResource = asset('fileResource', 'div');

const DocumentReference = Node.create({
  name: 'documentReference', group: 'inline', inline: true, atom: true, selectable: true, marks: '',
  addOptions() { return { resolveReference: async () => null }; },
  addAttributes() { return { resourceId: { default: null } }; },
  parseHTML() { return [{ tag: 'span[data-document-reference]', getAttrs: element => ({
    resourceId: element.getAttribute('data-document-reference'),
  }) }]; },
  renderHTML({ node }) { return ['span', { 'data-document-reference': node.attrs.resourceId }, '引用文档']; },
  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement('span');
      dom.className = 'document-reference'; dom.contentEditable = 'false';
      dom.dataset.documentReference = node.attrs.resourceId;
      const link = document.createElement('a');
      link.href = `/#resource/${encodeURIComponent(node.attrs.resourceId)}`;
      link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.textContent = '▤ 正在读取文档…'; dom.append(link);
      let destroyed = false;
      Promise.resolve(this.options.resolveReference(node.attrs.resourceId)).then(title => {
        if (destroyed) return;
        link.textContent = title ? `▤ ${title}` : '▤ 文档不可用';
        if (!title) link.removeAttribute('href');
      }).catch(() => {
        if (!destroyed) { link.textContent = '▤ 文档不可用'; link.removeAttribute('href'); }
      });
      return { dom, ignoreMutation: () => true,
        stopEvent: event => link.contains(event.target),
        destroy: () => { destroyed = true; } };
    };
  },
});

const safeCellColor = value => typeof value === 'string' && /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(value) ? value : null;
const cellBackground = {
  default: null,
  parseHTML: element => safeCellColor(element.getAttribute('data-background')),
  renderHTML: attributes => {
    const color = safeCellColor(attributes.background);
    return color ? { 'data-background': color, style: `background-color: ${color}` } : {};
  },
};
const BackgroundTableCell = TableCell.extend({ addAttributes() { return { ...this.parent?.(), background: cellBackground }; } });
const BackgroundTableHeader = TableHeader.extend({ addAttributes() { return { ...this.parent?.(), background: cellBackground }; } });

export function createDocumentExtensions({ editable = true, onMathClick = () => {}, documentId = '', resolveReference = async () => null, collaboration = null } = {}) {
  return [
    StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] }, undoRedo: !collaboration }),
    ...(collaboration ? [Collaboration.configure({ document: collaboration, field: 'prosemirror' })] : []),
    UniqueID.configure({ types: documentBlockTypes, updateDocument: editable }),
    TableKit.configure({ tableCell: false, tableHeader: false }),
    BackgroundTableCell, BackgroundTableHeader,
    ImageResource.configure({ documentId }), FileResource.configure({ documentId }),
    DocumentReference.configure({ resolveReference }),
    Mathematics.configure({
      katexOptions: { throwOnError: false, trust: false, maxExpand: 1000, maxSize: 20 },
      inlineOptions: { onClick: onMathClick },
      blockOptions: { onClick: onMathClick },
    }),
    Markdown,
  ];
}
