import type { ReactNode } from "react";

// The model writes Markdown. This draws the parts it uses as React elements, never as HTML, so a
// tag in an answer stays text. Only http(s) links become links. No library, for this small subset.

type ListNode = { ordered: boolean; start: number; items: { text: string; children: ListNode[] }[] };
type Block =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; text: string }
  | { kind: "rule" }
  | { kind: "list"; list: ListNode }
  | { kind: "table"; header: string[]; rows: string[][] };

const FENCE = /^\s*```/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;
const RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
const ITEM = /^(\s*)([-*•]|\d+[.)])\s+(.*)$/;
const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;
// Code, bold, a link, a bare address, or italic. Italic keeps the character before it in a group.
const INLINE =
  /`([^`\n]+)`|\*\*(.+?)\*\*|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<>)\]]+)|(^|[\s(])\*([^\s*][^*\n]*?)\*(?=[\s).,;:!?]|$)/g;

function isTableStart(lines: string[], i: number) {
  return lines[i].includes("|") && i + 1 < lines.length && lines[i + 1].includes("-") && TABLE_RULE.test(lines[i + 1]);
}

function cells(line: string) {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function startsBlock(lines: string[], i: number) {
  const line = lines[i];
  return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || ITEM.test(line) || isTableStart(lines, i);
}

function nextFilled(lines: string[], i: number) {
  while (i < lines.length && !lines[i].trim()) i++;
  return i;
}

/** Reads the list items at one indent. Deeper items become children of the item before them. */
function readList(lines: string[], from: number, indent: number): { list: ListNode; next: number } {
  const first = lines[from].match(ITEM)!;
  const ordered = /\d/.test(first[2]);
  const list: ListNode = { ordered, start: ordered ? parseInt(first[2], 10) : 1, items: [] };
  let i = from;
  while (i < lines.length) {
    const filled = nextFilled(lines, i);
    if (filled >= lines.length) return { list, next: filled };
    const item = lines[filled].match(ITEM);
    const at = item ? item[1].length : lines[filled].search(/\S/);
    if (!item) {
      // A line right under an item continues its text. After a blank line, only an indented one does.
      const last = list.items[list.items.length - 1];
      if (!last || startsBlock(lines, filled) || (filled > i && at <= indent)) return { list, next: i };
      last.text += `\n${lines[filled].trim()}`;
      i = filled + 1;
    } else if (at < indent || (at === indent && /\d/.test(item[2]) !== ordered)) {
      return { list, next: i };
    } else if (at > indent && list.items.length) {
      const child = readList(lines, filled, at);
      list.items[list.items.length - 1].children.push(child.list);
      i = child.next;
    } else {
      list.items.push({ text: item[3], children: [] });
      i = filled + 1;
    }
  }
  return { list, next: i };
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
    } else if (FENCE.test(line)) {
      const code: string[] = [];
      for (i++; i < lines.length && !FENCE.test(lines[i]); i++) code.push(lines[i]);
      i++;
      blocks.push({ kind: "code", text: code.join("\n") });
    } else if (HEADING.test(line)) {
      blocks.push({ kind: "heading", text: line.match(HEADING)![1] });
      i++;
    } else if (RULE.test(line)) {
      blocks.push({ kind: "rule" });
      i++;
    } else if (isTableStart(lines, i)) {
      const header = cells(line);
      const rows: string[][] = [];
      for (i += 2; i < lines.length && lines[i].includes("|"); i++) rows.push(cells(lines[i]));
      blocks.push({ kind: "table", header, rows });
    } else if (ITEM.test(line)) {
      const { list, next } = readList(lines, i, line.match(ITEM)![1].length);
      blocks.push({ kind: "list", list });
      i = next;
    } else {
      const paragraph: string[] = [];
      while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) paragraph.push(lines[i++].trim());
      blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
    }
  }
  return blocks;
}

function link(href: string, children: ReactNode, key: number) {
  return (
    <a key={key} href={href} target="_blank" rel="noopener noreferrer" className="break-all text-accent-text underline">
      {children}
    </a>
  );
}

/** Text between the marks. The model writes \\* for a star that is not a mark. */
const plain = (text: string) => text.replace(/\\([*`_])/g, "$1");

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(INLINE)) {
    const [whole, code, bold, label, href, bare, before, italic] = match;
    nodes.push(plain(text.slice(last, match.index)));
    last = match.index + whole.length;
    if (code !== undefined) {
      nodes.push(<code key={key++}>{code}</code>);
    } else if (bold !== undefined) {
      nodes.push(<strong key={key++}>{inline(bold)}</strong>);
    } else if (href !== undefined) {
      nodes.push(link(href, inline(label), key++));
    } else if (bare !== undefined) {
      // A sentence can end right after an address: the full stop is not part of it.
      const url = bare.replace(/[.,;:!?]+$/, "");
      nodes.push(link(url, url, key++), bare.slice(url.length));
    } else {
      nodes.push(before, <em key={key++}>{inline(italic)}</em>);
    }
  }
  nodes.push(plain(text.slice(last)));
  return nodes;
}

function List({ list }: { list: ListNode }) {
  const Tag = list.ordered ? "ol" : "ul";
  return (
    <Tag
      start={list.ordered ? list.start : undefined}
      className={`space-y-1 pl-5 ${list.ordered ? "list-decimal" : "list-disc"}`}
    >
      {list.items.map((item, i) => (
        <li key={i}>
          <span className="whitespace-pre-wrap">{inline(item.text)}</span>
          {item.children.map((child, j) => (
            <div key={j} className="mt-1">
              <List list={child} />
            </div>
          ))}
        </li>
      ))}
    </Tag>
  );
}

export function AgentText({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm">
      {parseBlocks(text).map((block, i) => {
        switch (block.kind) {
          case "heading":
            return (
              <h3 key={i} className="pt-1 font-semibold">
                {inline(block.text)}
              </h3>
            );
          case "paragraph":
            return (
              <p key={i} className="whitespace-pre-wrap">
                {inline(block.text)}
              </p>
            );
          case "code":
            return (
              <pre key={i} className="overflow-x-auto rounded-md bg-surface-2 p-2 text-xs">
                {block.text}
              </pre>
            );
          case "rule":
            return <hr key={i} className="border-line" />;
          case "list":
            return <List key={i} list={block.list} />;
          case "table":
            return (
              <div key={i} className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted">
                    <tr>
                      {block.header.map((cell, j) => (
                        <th key={j} className="py-1 pr-3 font-normal">
                          {inline(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, j) => (
                      <tr key={j} className="border-t border-line">
                        {row.map((cell, k) => (
                          <td key={k} className="py-1 pr-3">
                            {inline(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
