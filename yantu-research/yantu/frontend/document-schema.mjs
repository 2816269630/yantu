import StarterKit from '@tiptap/starter-kit';
import { Mathematics } from '@tiptap/extension-mathematics';
import { TableKit, TableCell, TableHeader } from '@tiptap/extension-table';
import { UniqueID } from '@tiptap/extension-unique-id';
import { Markdown } from '@tiptap/markdown';

export const documentBlockTypes = [
  'paragraph', 'heading', 'bulletList', 'orderedList', 'listItem',
  'blockquote', 'codeBlock', 'horizontalRule', 'blockMath',
  'table', 'tableRow', 'tableCell', 'tableHeader',
];

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

export function createDocumentExtensions({ editable = true, onMathClick = () => {} } = {}) {
  return [
    StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] } }),
    UniqueID.configure({ types: documentBlockTypes, updateDocument: editable }),
    TableKit.configure({ tableCell: false, tableHeader: false }),
    BackgroundTableCell, BackgroundTableHeader,
    Mathematics.configure({
      katexOptions: { throwOnError: false, trust: false, maxExpand: 1000, maxSize: 20 },
      inlineOptions: { onClick: onMathClick },
      blockOptions: { onClick: onMathClick },
    }),
    Markdown,
  ];
}
