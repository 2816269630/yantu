'use strict';

function documentMath(tex, displayMode=false) {
  const source=String(tex||'').trim();
  if(!source)return '';
  if(!window.katex)return `<code class="document-math-fallback">${esc(source)}</code>`;
  try {return window.katex.renderToString(source,{displayMode,throwOnError:false,trust:false,maxExpand:1000,maxSize:20});}
  catch {return `<code class="document-math-fallback">${esc(source)}</code>`;}
}
function documentPlain(text) {
  return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
}
function documentInline(text,line=-1) {
  const source=String(text||''),parts=[];
  const math=/\\\((.+?)\\\)|(?<!\\)\$([^$\n]+?)\$(?!\$)/g;
  let start=0,match,index=0;
  while((match=math.exec(source))){
    parts.push(documentPlain(source.slice(start,match.index)));
    const mathHtml=documentMath(match[1]??match[2]);
    parts.push(line<0?mathHtml:`<span class="document-formula-target" data-doc-math-line="${line}" data-doc-math-index="${index++}" data-doc-math-source="${esc(match[1]??match[2])}" contenteditable="false" role="button" tabindex="0" title="点击编辑公式" aria-label="编辑公式">${mathHtml}</span>`);
    start=math.lastIndex;
  }
  parts.push(documentPlain(source.slice(start)));
  return parts.join('');
}
function renderDocumentPreview(body) {
  const lines=String(body||'').replace(/\r/g,'').split('\n'),html=[];
  const heading=/^\s{0,3}(#{1,6})\s+(.+?)\s*$/;
  const bullet=/^\s*[-*+]\s+(.+)$/;
  const numbered=/^\s*\d+\.\s+(.+)$/;
  const special=line=>!line.trim()||heading.test(line)||bullet.test(line)||numbered.test(line)||/^\s*```/.test(line)||/^\s*(?:\$\$|\\\[)/.test(line)||/^\s*>/.test(line);
  for(let i=0;i<lines.length;){
    const raw=lines[i],trimmed=raw.trim();
    if(!trimmed){i++;continue;}
    const mathStart=trimmed.startsWith('$$')?'$$':trimmed.startsWith('\\[')?'\\[':null;
    if(mathStart){
      const end=mathStart==='$$'?'$$':'\\]';
      const after=trimmed.slice(mathStart.length),close=after.indexOf(end);
      if(close>=0){html.push(`<div class="document-math-block document-formula-target" data-doc-line="${i}" data-doc-math-block="${i}" role="button" tabindex="0" title="点击编辑公式" aria-label="编辑公式">${documentMath(after.slice(0,close),true)}</div>`);i++;continue;}
      const source=[after];let j=i+1;
      while(j<lines.length&&!lines[j].includes(end)){source.push(lines[j]);j++;}
      if(j<lines.length){source.push(lines[j].slice(0,lines[j].indexOf(end)));html.push(`<div class="document-math-block document-formula-target" data-doc-line="${i}" data-doc-math-block="${i}" role="button" tabindex="0" title="点击编辑公式" aria-label="编辑公式">${documentMath(source.join('\n'),true)}</div>`);i=j+1;continue;}
    }
    if(/^\s*```/.test(raw)){
      const language=trimmed.slice(3).trim(),code=[];let j=i+1;
      while(j<lines.length&&!/^\s*```/.test(lines[j]))code.push(lines[j++]);
      html.push(`<pre data-doc-editable data-doc-line="${i}" data-doc-end-line="${j<lines.length?j:j-1}"><code>${esc(code.join('\n'))}</code></pre>`);i=j<lines.length?j+1:j;continue;
    }
    const title=raw.match(heading);
    if(title){const level=title[1].length;html.push(`<h${level} data-doc-editable data-doc-line="${i}" data-doc-end-line="${i}">${documentInline(title[2].replace(/\s+#+\s*$/,''),i)}</h${level}>`);i++;continue;}
    const list=raw.match(bullet)||raw.match(numbered);
    if(list){const ordered=Boolean(raw.match(numbered)),tag=ordered?'ol':'ul',items=[];
      while(i<lines.length){const item=lines[i].match(ordered?numbered:bullet);if(!item)break;items.push(`<li data-doc-editable data-doc-line="${i}" data-doc-end-line="${i}">${documentInline(item[1],i)}</li>`);i++;}
      html.push(`<${tag}>${items.join('')}</${tag}>`);continue;
    }
    if(/^\s*>/.test(raw)){const quotes=[],start=i;while(i<lines.length&&/^\s*>/.test(lines[i])){quotes.push(documentInline(lines[i].replace(/^\s*>\s?/,''),i));i++;}html.push(`<blockquote data-doc-editable data-doc-line="${start}" data-doc-end-line="${i-1}">${quotes.join(' ')}</blockquote>`);continue;}
    const paragraph=[],start=i;
    while(i<lines.length&&!special(lines[i]))paragraph.push(lines[i++]);
    if(paragraph.length)html.push(`<p data-doc-editable data-doc-line="${start}" data-doc-end-line="${i-1}">${paragraph.map((text,offset)=>documentInline(text,start+offset)).join(' ')}</p>`);
    else {html.push(`<p data-doc-editable data-doc-line="${i}" data-doc-end-line="${i}">${documentInline(lines[i],i)}</p>`);i++;}
  }
  return html.join('')||'<p class="document-preview-empty" data-doc-editable data-doc-line="0" data-doc-end-line="0">从这里开始书写…</p>';
}
