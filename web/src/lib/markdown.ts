/** 브리핑 마크다운 → HTML (제목 · 목록 · 표 · 굵게 · 인용 · 근거 번호). 입력은 먼저 이스케이프한다 */
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
function inline(s: string, known: Set<string>) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\b([EI]-\d{3}|SIG-\d{5})\b/g, (m) => `<a class="ev${known.has(m) ? "" : " ev-none"}" data-ev="${m}" role="button" tabindex="0">${m}</a>`);
}
export function renderMarkdown(text: string, known: Set<string>) {
  const out: string[] = []; let para: string[] = [], list: "ul" | "ol" | null = null, table: string[] = [];
  const flush = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "), known)}</p>`); para = []; }
    if (list) { out.push(`</${list}>`); list = null; }
    if (table.length) {
      const rows = table.map((r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim())).filter((r) => !r.every((c) => /^:?-+:?$/.test(c || "-")));
      out.push(`<div class="tw"><table>${rows.map((r, i) => `<tr>${r.map((c) => `<${i ? "td" : "th"}>${inline(c, known)}</${i ? "td" : "th"}>`).join("")}</tr>`).join("")}</table></div>`);
      table = [];
    }
  };
  for (const raw of text.split("\n")) {
    const s = raw.trim();
    if (!s) { flush(); continue; }
    if (s.startsWith("|")) { if (para.length || list) flush(); table.push(s); continue; }
    if (table.length) flush();
    let m = s.match(/^(#{1,4})\s+(.*)/);
    if (m) { flush(); out.push(`<h${m[1].length}>${inline(m[2], known)}</h${m[1].length}>`); continue; }
    m = s.match(/^(?:[-*]|(\d+)[.)])\s+(.*)/);
    if (m) { const kind = m[1] ? "ol" : "ul"; if (para.length) flush(); if (list !== kind) { if (list) out.push(`</${list}>`); out.push(`<${kind}>`); list = kind; } out.push(`<li>${inline(m[2], known)}</li>`); continue; }
    if (s.startsWith(">")) { flush(); out.push(`<blockquote>${inline(s.replace(/^>\s*/, ""), known)}</blockquote>`); continue; }
    if (list) flush();
    para.push(s);
  }
  flush();
  return out.join("\n");
}
/** 줄 단위 비교 (지운 줄 · 새 줄) */
export function lineDiff(a: string, b: string) {
  const A = a.split("\n"), B = b.split("\n"), n = A.length, m = B.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: { t: "same" | "del" | "add"; s: string }[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) { if (A[i] === B[j]) { out.push({ t: "same", s: A[i] }); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: "del", s: A[i++] }); else out.push({ t: "add", s: B[j++] }); }
  while (i < n) out.push({ t: "del", s: A[i++] });
  while (j < m) out.push({ t: "add", s: B[j++] });
  return out;
}
