import StarterKit from '@tiptap/starter-kit';
import { Mathematics } from '@tiptap/extension-mathematics';
import { TableKit, TableCell, TableHeader } from '@tiptap/extension-table';
import { UniqueID } from '@tiptap/extension-unique-id';
import { Markdown } from '@tiptap/markdown';
import { Node } from '@tiptap/core';

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

export function createDocumentExtensions({ editable = true, onMathClick = () => {}, documentId = '' } = {}) {
  return [
    StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] } }),
    UniqueID.configure({ types: documentBlockTypes, updateDocument: editable }),
    TableKit.configure({ tableCell: false, tableHeader: false }),
    BackgroundTableCell, BackgroundTableHeader,
    ImageResource.configure({ documentId }), FileResource.configure({ documentId }),
    Mathematics.configure({
      katexOptions: { throwOnError: false, trust: false, maxExpand: 1000, maxSize: 20 },
      inlineOptions: { onClick: onMathClick },
      blockOptions: { onClick: onMathClick },
    }),
    Markdown,
  ];
}
