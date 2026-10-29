import { type ReactNode } from 'react';

type Block =
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'heading'; text: string }
  | { kind: 'list'; numbered: boolean; items: string[] }
  | { kind: 'code'; text: string };

function inline(text: string): ReactNode[] {
  const pieces: ReactNode[] = [];
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index;
    if (index > last) pieces.push(text.slice(last, index));
    const value = match[0];
    const key = pieces.length;
    if (value.startsWith('**')) {
      pieces.push(<strong key={key}>{value.slice(2, -2)}</strong>);
    } else if (value.startsWith('`')) {
      pieces.push(<code key={key}>{value.slice(1, -1)}</code>);
    } else {
      pieces.push(<em key={key}>{value.slice(1, -1)}</em>);
    }
    last = index + value.length;
  }
  if (last < text.length) pieces.push(text.slice(last));
  return pieces;
}

function parse(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { numbered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', lines: paragraph });
    if (list) blocks.push({ kind: 'list', ...list });
    paragraph = [];
    list = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith('```')) {
      flush();
      const code: string[] = [];
      while (++i < lines.length && !lines[i].trim().startsWith('```')) {
        code.push(lines[i]);
      }
      blocks.push({ kind: 'code', text: code.join('\n') });
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = /^#{1,4}\s+(.+)$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: 'heading', text: heading[1] });
      continue;
    }
    const bullet = /^\s*([-*]|\d+[.)])\s+(.+)$/.exec(line);
    if (bullet) {
      if (paragraph.length) flush();
      const numbered = /^\d/.test(bullet[1]);
      if (list && list.numbered !== numbered) flush();
      if (!list) list = { numbered, items: [] };
      list.items.push(bullet[2]);
      continue;
    }
    if (list) flush();
    paragraph.push(line);
  }
  flush();
  return blocks;
}

/** Read-only Markdown subset. Never insert HTML or follow untrusted links. */
export function MarkdownMessage({ content }: { content: string }) {
  const blocks = parse(content);
  return (
    <div className="chat-markdown">
      {blocks.map((block, index) => {
        if (block.kind === 'code') {
          return <pre key={index}><code>{block.text}</code></pre>;
        }
        if (block.kind === 'heading') {
          return <h4 key={index}>{inline(block.text)}</h4>;
        }
        if (block.kind === 'list') {
          const items = block.items.map((item, i) => <li key={i}>{inline(item)}</li>);
          return block.numbered
            ? <ol key={index}>{items}</ol>
            : <ul key={index}>{items}</ul>;
        }
        return <p key={index}>{block.lines.map((line, i) => (
          <span key={i}>{i > 0 ? <span className="chat-line-break" /> : null}{inline(line)}</span>
        ))}</p>;
      })}
    </div>
  );
}
