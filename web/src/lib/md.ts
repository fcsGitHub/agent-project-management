/** GFM read-only rendering for item comments (M20-I64, docs/01 §S.3). The
 * stored body stays plain text — this is purely a render-layer transform.
 * marked (GFM) + DOMPurify (XSS fail-closed); @Name mentions become chips
 * (longest-name-first, same precision rule as the backend mention parser). */
import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: true });

let hookInstalled = false;
function installLinkHook() {
  if (hookInstalled) return;
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.getAttribute("href")) {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer nofollow");
    }
    // task-list checkboxes are the only inputs allowed through (read-only)
    if (node.tagName === "INPUT" && node.getAttribute("type") !== "checkbox") {
      node.remove();
    }
  });
  hookInstalled = true;
}

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export type MdRenderOpts = {
  /** task-list text → created work-item id (I67 extraction) */
  extracted?: Map<string, string>;
  /** render an explicit "转为子任务" button on un-extracted task items */
  extractable?: boolean;
  /** e.g. `#/p/{pid}/board` — extraction links point at `?item=` */
  boardPath?: string;
};

export function renderCommentMd(body: string, names: string[], opts?: MdRenderOpts): string {
  installLinkHook();
  // tokenize mentions before markdown so chips survive tables/quotes as text;
  // names are escaped when re-injected post-sanitize (fixed markup, ours).
  const sorted = [...names].sort((a, b) => b.length - a.length)
    .filter((n) => body.includes(`@${n}`));
  const tokenized = sorted.length
    ? body.replace(new RegExp(`@(?:${sorted.map(escapeRe).join("|")})`, "g"),
      (m) => `@@m:${m.slice(1)}@@`)
    : body;
  const html = marked.parse(tokenized, { async: false }) as string;
  // form forbidden + the hook keeps only disabled task-list checkboxes
  const clean = DOMPurify.sanitize(html, {
    FORBID_TAGS: ["style", "form"],
    FORBID_ATTR: ["style"],
  });
  // I67: task-list items become extraction widgets — extracted texts link to
  // their work item, un-extracted ones get an explicit (click, not hover)
  // convert button. Buttons are fixed markup with escaped attr values; the
  // click is handled via delegation in CommentsModal.
  let out = clean;
  if (opts?.extracted?.size || opts?.extractable) {
    out = out.replace(/<li>\s*(<input[^>]*type="checkbox"[^>]*>)\s*([\s\S]*?)<\/li>/g,
      (m, input: string, inner: string) => {
        const text = inner.replace(/<[^>]+>/g, "").trim();
        const itemId = opts?.extracted?.get(text);
        if (itemId) {
          const href = opts?.boardPath
            ? `${opts.boardPath}?item=${encodeURIComponent(itemId)}`
            : "#";
          // boardPath 来自路由参数（pid），拼接发生在 sanitize 之后——必须整体
          // 转义，防构造含引号的 pid 闭合属性注入事件处理器。
          return `<li>${input} <a href="${escapeHtml(href)}" class="text-acc underline">🔗 ${escapeHtml(text)}</a>`
            + ` <span class="rounded bg-accbg px-1 text-[10px] font-medium text-acc">已提取</span></li>`;
        }
        if (opts?.extractable) {
          return `<li>${input} ${inner}`
            + `<button type="button" data-extract="${escapeHtml(text)}"`
            + ` class="ml-1 rounded border border-line px-1 text-[10px] text-mut hover:border-acc hover:text-acc">转为子任务</button></li>`;
        }
        return m;
      });
  }
  return out.replace(/@@m:(.*?)@@/g, (_m, name: string) =>
    `<span class="rounded bg-accbg px-1 font-medium text-acc">@${escapeHtml(name)}</span>`);
}
