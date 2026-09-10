import type { ReactNode } from "react";

/**
 * Lightweight markdown renderer for notes/help text.
 *
 * Supports a small, safe subset of CommonMark used by the water-management
 * notes (no HTML, no raw links to avoid XSS):
 *   - `#` / `##` headings
 *   - `* item` / `- item` bullet lists (single level)
 *   - `1. item` numbered lists (single level)
 *   - `**bold**`, `*italic*`, `` `code` ``, `[text](url)`
 *   - blank-line separated paragraphs
 *
 * Reusable anywhere the app needs to show user-authored markdown notes.
 */
export function MarkdownNotes({ markdown }: { markdown: string }) {
  if (!markdown) return null;

  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: ReactNode[] } | null = null;
  let key = 0;

  const flushList = () => {
    if (!list) return;
    const { ordered, items } = list;
    blocks.push(
      ordered ? (
        <ol key={key++}>{items.map((it, i) => <li key={i}>{it}</li>)}</ol>
      ) : (
        <ul key={key++}>{items.map((it, i) => <li key={i}>{it}</li>)}</ul>
      )
    );
    list = null;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    // blank line -> flush any open list and move on
    if (line.trim() === "") {
      flushList();
      continue;
    }

    // headings
    const h = /^(#{1,6})\s+(.*)$/.exec(line.trim());
    if (h) {
      flushList();
      const level = h[1].length;
      const Tag = (`h${level}`) as keyof React.JSX.IntrinsicElements;
      blocks.push(<Tag key={key++}>{inline(h[2])}</Tag>);
      continue;
    }

    // bullet list
    const b = /^[-*]\s+(.*)$/.exec(line.trim());
    if (b) {
      if (!list) list = { ordered: false, items: [] };
      list.items.push(inline(b[1]));
      continue;
    }

    // numbered list
    const n = /^\d+\.\s+(.*)$/.exec(line.trim());
    if (n) {
      if (!list) list = { ordered: true, items: [] };
      list.items.push(inline(n[1]));
      continue;
    }

    // paragraph (flush any open list first)
    flushList();
    blocks.push(<p key={key++}>{inline(line.trim())}</p>);
  }
  flushList();

  return <div className="markdown-notes">{blocks}</div>;
}

/** Render inline markdown (bold, italic, code, links) to React nodes. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const match = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)!;
      out.push(
        <a key={k++} href={match[2]} target="_blank" rel="noreferrer">{match[1]}</a>
      );
    } else if (tok.startsWith("*")) out.push(<em key={k++}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}