"""Versioned content model for native .ytdoc documents.

Version 1 is kept readable for documents written by v0.3.3. New writes use
version 2, where editable blocks have stable IDs and tables are first-class
children instead of Markdown text.
"""
from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException


BLOCK_TYPES = {
    'paragraph', 'heading', 'bulletList', 'orderedList', 'listItem',
    'blockquote', 'codeBlock', 'horizontalRule', 'blockMath',
    'table', 'tableRow', 'tableCell', 'tableHeader',
}
INLINE_TYPES = {'text', 'hardBreak', 'inlineMath'}
CHILDREN = {
    'doc': {'paragraph', 'heading', 'bulletList', 'orderedList', 'blockquote',
            'codeBlock', 'horizontalRule', 'blockMath', 'table'},
    'paragraph': INLINE_TYPES,
    'heading': INLINE_TYPES,
    'bulletList': {'listItem'},
    'orderedList': {'listItem'},
    'listItem': {'paragraph', 'bulletList', 'orderedList', 'blockquote', 'codeBlock', 'table'},
    'blockquote': {'paragraph', 'heading', 'bulletList', 'orderedList', 'codeBlock',
                   'horizontalRule', 'blockMath', 'table'},
    'codeBlock': {'text'},
    'table': {'tableRow'},
    'tableRow': {'tableCell', 'tableHeader'},
    'tableCell': {'paragraph', 'heading', 'bulletList', 'orderedList', 'blockquote',
                  'codeBlock', 'horizontalRule', 'blockMath'},
    'tableHeader': {'paragraph', 'heading', 'bulletList', 'orderedList', 'blockquote',
                    'codeBlock', 'horizontalRule', 'blockMath'},
    'text': set(), 'hardBreak': set(), 'inlineMath': set(),
    'horizontalRule': set(), 'blockMath': set(),
}
MARKS = {'bold', 'italic', 'strike', 'code', 'underline', 'link'}
NODE_ATTRS = {
    'doc': set(), 'paragraph': {'id'}, 'heading': {'id', 'level'},
    'bulletList': {'id'}, 'orderedList': {'id', 'start', 'type'},
    'listItem': {'id'}, 'blockquote': {'id'}, 'codeBlock': {'id', 'language'},
    'horizontalRule': {'id'}, 'blockMath': {'id', 'latex'},
    'table': {'id'}, 'tableRow': {'id'},
    'tableCell': {'id', 'colspan', 'rowspan', 'colwidth', 'background', 'align'},
    'tableHeader': {'id', 'colspan', 'rowspan', 'colwidth', 'background', 'align'},
    'text': set(), 'hardBreak': set(), 'inlineMath': {'latex'},
}


def new_document():
    return {'schemaVersion': 2, 'type': 'doc', 'content': [
        {'type': 'paragraph', 'attrs': {'id': str(uuid4())}},
    ]}


def _invalid(message='文档结构无效'):
    raise HTTPException(400, message)


def _safe_link(href):
    if not isinstance(href, str) or not href or len(href) > 2048 or any(ord(ch) < 32 for ch in href):
        return False
    try:
        parsed = urlsplit(href)
    except ValueError:
        return False
    if parsed.scheme in ('http', 'https'):
        return bool(parsed.netloc)
    return parsed.scheme == 'mailto' and bool(parsed.path)


def validate_document(content, *, for_write=False):
    """Return the unchanged JSON and searchable text after structural checks."""
    if not isinstance(content, dict) or content.get('type') != 'doc':
        _invalid()
    version = content.get('schemaVersion')
    if type(version) is not int or version not in (1, 2):
        _invalid('不支持的文档结构版本')
    if for_write and version != 2:
        _invalid('请先升级文档内容格式')
    if set(content) != {'schemaVersion', 'type', 'content'}:
        _invalid()

    seen_ids = set()
    text_parts = []
    count = 0

    def visit(node, parent=None, depth=0):
        nonlocal count
        if depth > 32 or not isinstance(node, dict):
            _invalid()
        kind = node.get('type')
        if not isinstance(kind, str) or kind not in CHILDREN or (parent and kind not in CHILDREN[parent]):
            _invalid()
        if kind == 'doc' and parent is not None:
            _invalid()
        allowed_keys = {'type', 'attrs', 'content', 'text', 'marks'}
        if kind == 'doc':
            allowed_keys.add('schemaVersion')
        if not set(node) <= allowed_keys:
            _invalid()
        attrs = node.get('attrs', {})
        if not isinstance(attrs, dict):
            _invalid('文档属性无效')
        if version == 2:
            if not set(attrs) <= NODE_ATTRS[kind]:
                _invalid('文档属性无效')
            if kind in BLOCK_TYPES:
                identifier = attrs.get('id')
                if not isinstance(identifier, str):
                    _invalid('文档块缺少标识')
                try:
                    if str(UUID(identifier)) != identifier:
                        _invalid('文档块标识无效')
                except ValueError:
                    _invalid('文档块标识无效')
                if identifier in seen_ids:
                    _invalid('文档块标识重复')
                seen_ids.add(identifier)
            elif 'id' in attrs:
                _invalid('文档属性无效')
        if kind == 'heading' and (type(attrs.get('level')) is not int or not 1 <= attrs['level'] <= 6):
            _invalid('标题级别无效')
        if kind in ('inlineMath', 'blockMath'):
            latex = attrs.get('latex')
            if not isinstance(latex, str) or len(latex) > 5000:
                _invalid('公式内容无效')
            text_parts.append(latex)
            count += len(latex)
        if kind == 'text':
            value = node.get('text')
            if not isinstance(value, str):
                _invalid('文档文本无效')
            text_parts.append(value)
            count += len(value)
            marks = node.get('marks', [])
            if not isinstance(marks, list):
                _invalid('文档格式无效')
            for mark in marks:
                if not isinstance(mark, dict) or not isinstance(mark.get('type'), str) or mark['type'] not in MARKS:
                    _invalid('文档格式无效')
                if mark['type'] == 'link':
                    link_attrs = mark.get('attrs')
                    if (not isinstance(link_attrs, dict) or not set(link_attrs) <= {'href', 'target', 'rel', 'class', 'title'}
                            or not _safe_link(link_attrs.get('href'))):
                        _invalid('链接地址无效')
                    if any(value is not None and not isinstance(value, str) for value in link_attrs.values()):
                        _invalid('链接地址无效')
                    if link_attrs.get('target') not in (None, '_blank', '_self') or any(
                        len(value) > 200 for key, value in link_attrs.items() if key != 'href' and isinstance(value, str)
                    ):
                        _invalid('链接地址无效')
                elif version == 2 and set(mark) != {'type'}:
                    _invalid('文档格式无效')
        elif 'text' in node or 'marks' in node:
            _invalid()
        children = node.get('content', [])
        if not isinstance(children, list) or len(children) > 10000:
            _invalid()
        if kind in ('text', 'hardBreak', 'inlineMath', 'horizontalRule', 'blockMath') and children:
            _invalid()
        if kind in ('doc', 'bulletList', 'orderedList', 'listItem', 'table', 'tableRow', 'tableCell', 'tableHeader') and not children:
            _invalid()
        if kind == 'table' and (len(children) > 100 or not all(row.get('type') == 'tableRow' for row in children if isinstance(row, dict))):
            _invalid('表格最多 100 行')
        if kind == 'tableRow':
            columns = 0
            for cell in children:
                if not isinstance(cell, dict):
                    _invalid()
                cell_attrs = cell.get('attrs', {})
                if not isinstance(cell_attrs, dict) or type(cell_attrs.get('colspan', 1)) is not int:
                    _invalid('表格单元格无效')
                columns += cell_attrs.get('colspan', 1)
            if columns > 20:
                _invalid('表格最多 20 列')
        if kind in ('tableCell', 'tableHeader'):
            for name in ('colspan', 'rowspan'):
                value = attrs.get(name, 1)
                if type(value) is not int or not 1 <= value <= 20:
                    _invalid('表格单元格无效')
            widths = attrs.get('colwidth')
            if widths is not None and (not isinstance(widths, list) or len(widths) > 20 or
                                       any(type(width) is not int or not 1 <= width <= 4000 for width in widths)):
                _invalid('表格列宽无效')
        if kind == 'orderedList' and (type(attrs.get('start', 1)) is not int or attrs.get('start', 1) < 1):
            _invalid('列表序号无效')
        if kind == 'orderedList' and attrs.get('type') is not None and (
            not isinstance(attrs['type'], str) or len(attrs['type']) > 20
        ):
            _invalid('列表类型无效')
        if kind == 'codeBlock' and attrs.get('language') is not None and (
            not isinstance(attrs['language'], str) or len(attrs['language']) > 40
        ):
            _invalid('代码语言无效')
        if kind in ('tableCell', 'tableHeader') and attrs.get('background') is not None:
            background = attrs['background']
            if not isinstance(background, str) or not (
                len(background) in (4, 7) and background.startswith('#') and
                all(ch in '0123456789abcdefABCDEF' for ch in background[1:])
            ):
                _invalid('表格背景色无效')
        if kind in ('tableCell', 'tableHeader') and attrs.get('align') not in (None, 'left', 'center', 'right'):
            _invalid('表格对齐方式无效')
        for child in children:
            visit(child, kind, depth + 1)
        count += 1
        if count > 200000:
            _invalid('文档内容最多 20 万字')

    visit(content)
    return content, ' '.join(text_parts)
