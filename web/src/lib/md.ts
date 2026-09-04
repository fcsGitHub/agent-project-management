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
  });
  hookInstalled = true;
}

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function renderCommentMd(body: string, names: string[]): string {
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
  const clean = DOMPurify.sanitize(html, {
    FORBID_TAGS: ["style", "form", "input"],
    FORBID_ATTR: ["style"],
  });
  return clean.replace(/@@m:(.*?)@@/g, (_m, name: string) =>
    `<span class="rounded bg-accbg px-1 font-medium text-acc">@${escapeHtml(name)}</span>`);
}
