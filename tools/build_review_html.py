# -*- coding: utf-8 -*-
"""Build a single-file review HTML from the design markdown docs.

Usage: python tools/build_review_html.py
Output: review.html (project root)

Markdown subset supported: ATX headings, fenced code, tables, blockquotes,
ordered/unordered lists (one nesting level), hr, bold, inline code, links.
Internal .md links are rewritten to in-page section anchors.
"""
import html
import pathlib
import re
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent

DOCS = [
    ("README.md", "00", "总览与核心决策"),
    ("docs/01-open-source-research.md", "01", "开源调研报告"),
    ("docs/02-overall-design.md", "02", "总体设计与架构"),
    ("docs/03-lifecycle-and-usage-flow.md", "03", "使用流程与层级模型"),
    ("docs/04-data-model-and-persistence.md", "04", "数据模型与持久化"),
    ("docs/05-hitl-trajectory-audit.md", "05", "人机协作·轨迹·审计"),
    ("docs/06-webui-design.md", "06", "WebUI 设计"),
    ("docs/07-mvp-and-roadmap.md", "07", "MVP 与扩展路线"),
    ("docs/08-ontology.md", "08", "项目本体模块"),
    ("docs/09-asset-library.md", "09", "资产库与知识沉淀"),
    ("docs/10-development-plan.md", "10", "开发计划与迭代审阅"),
]

STRUCT = re.compile(r"^(\s*)(#{1,6}\s+|```|\||>|[-*+]\s|\d+\.\s)")
SEP_ROW = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")


class Converter:
    def __init__(self, doc_key, md_paths):
        self.doc_key = doc_key
        # map of md file path -> section anchor, to rewrite internal links
        self.md_anchors = {p.replace("\\", "/"): f"#doc-{k}" for p, k, _ in md_paths}
        self.headings = []  # (level, text, id)

    # ---------- inline ----------
    def inline(self, s: str) -> str:
        s = html.escape(s, quote=False)
        stash = []

        def keep(m):
            stash.append(m.group(1))
            return f"\x00{len(stash) - 1}\x01"

        s = re.sub(r"`([^`]+)`", keep, s)

        def link(m):
            href = m.group(2)
            href = self.md_anchors.get(href, href)
            return f'<a href="{html.escape(href, quote=True)}">{m.group(1)}</a>'

        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\x00(\d+)\x01", lambda m: f"<code>{stash[int(m.group(1))]}</code>", s)
        return s

    # ---------- blocks ----------
    def split_row(self, line: str):
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    def table(self, header, rows):
        th = "".join(f"<th>{self.inline(c)}</th>" for c in header)
        trs = []
        for r in rows:
            tds = "".join(f"<td>{self.inline(c)}</td>" for c in r)
            trs.append(f"<tr>{tds}</tr>")
        return (
            '<div class="tbl"><table><thead><tr>'
            f"{th}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
        )

    def list_html(self, items):
        top_ordered = items[0][1]
        tag = "ol" if top_ordered else "ul"
        out = [f"<{tag}>"]
        for indent, ordered, content in items:
            if indent < 2:
                out.append(f"<li>{self.inline(content)}</li>")
            else:  # nest inside the previous <li>
                if out[-1].endswith("</li>"):
                    out[-1] = out[-1][: -len("</li>")]
                    sub = "ol" if ordered else "ul"
                    out[-1] += f"<{sub}><li>{self.inline(content)}</li></{sub}></li>"
                else:
                    out.append(f"<li>{self.inline(content)}</li>")
        out.append(f"</{tag}>")
        return "".join(out)

    def convert(self, text: str) -> str:
        lines = text.splitlines()
        out = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):  # fenced code
                code = []
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    code.append(lines[i])
                    i += 1
                i += 1
                body = html.escape("\n".join(code))
                out.append(f'<pre class="code"><code>{body}</code></pre>')
                continue

            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                level = min(len(m.group(1)), 4)
                hid = f"{self.doc_key}-h{len(self.headings)}"
                self.headings.append((level, m.group(2).strip(), hid))
                out.append(f'<h{level} id="{hid}">{self.inline(m.group(2).strip())}</h{level}>')
                i += 1
                continue

            if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
                out.append("<hr>")
                i += 1
                continue

            if stripped.startswith("|") and i + 1 < n and SEP_ROW.match(lines[i + 1]):
                header = self.split_row(line)
                i += 2
                rows = []
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(self.split_row(lines[i]))
                    i += 1
                out.append(self.table(header, rows))
                continue

            if stripped.startswith(">"):
                buf = []
                while i < n and lines[i].strip().startswith(">"):
                    buf.append(re.sub(r"^\s*>\s?", "", lines[i]).strip())
                    i += 1
                out.append("<blockquote>" + "<br>".join(self.inline(b) for b in buf) + "</blockquote>")
                continue

            if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
                items = []
                while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                    m2 = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[i])
                    items.append(
                        (len(m2.group(1)), bool(re.match(r"\d+\.", m2.group(2))), m2.group(3))
                    )
                    i += 1
                out.append(self.list_html(items))
                continue

            if not stripped:
                i += 1
                continue

            buf = [line.strip()]
            i += 1
            while i < n and lines[i].strip() and not STRUCT.match(lines[i]):
                buf.append(lines[i].strip())
                i += 1
            out.append(f"<p>{self.inline(' '.join(buf))}</p>")
        return "\n".join(out)


REQUIREMENT_ROWS = [
    ("r1", "需求 1", "调研 GitHub 开源项目（agent 框架 + 项目管理工具），吸取经验与可复用部分", "01"),
    ("r2", "需求 2", "使用流程设计：逻辑分层、持久化、人与 Agent 轨迹可视化、审计批准", "02 · 03 · 04 · 05"),
    ("r3", "需求 3", "覆盖需求 → 开发 → 测试 → 交付的典型管理路径", "03"),
    ("r4", "需求 4", "WebUI 架构：简洁高效、突出必要信息、功能收纳、兼顾新手与高级用户", "06"),
    ("r5", "需求 5", "人机协作：人安排 Agent 全流程高效工作，参考 graph engineering", "02 · 05"),
    ("r6", "需求 6", "最小化可实现版本（MVP）+ 可扩展性", "07"),
    ("rv1", "评审 1", "从用户使用流程梳理，明确典型使用流程", "03 §4（8 条详细剧本）"),
    ("rv2", "评审 2", "补充真实可用 agent 调研（deepseek harness、轨迹×图结合、pi 极简、dsh 插件化）", "01 C · 05 §3.5"),
    ("rv3", "评审 3", "项目下挂功能、功能下挂对话；提示词按层披露；持久化随时打断更改", "03 §1-§3 · 04"),
    ("rv4", "评审 4", "支持通过自然语言对页面进行操作", "06 §5 · 07"),
    ("rv5", "评审 5", "增加本体模块（参考 semantica 简化设计）", "08"),
    ("rv6", "评审 6", "累计资产设计：产品库/测试库/文档库，资产管理与检索，划归本体", "08 · 09"),
    ("d1", "开发要求", "制定可用于执行的开发计划：审阅迭代、持续推进完成开发；尽量复用开源成果", "07 §2.5 · 10"),
]

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentPM 方案设计 · 评审版</title>
<style>
:root{
  --bg:#f5f6f8; --panel:#ffffff; --ink:#1f2328; --muted:#66707a;
  --accent:#0b5fff; --accent-soft:#eef3ff; --border:#e3e6ea; --code-bg:#f6f8fa;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);background:var(--bg);
  font:15px/1.8 -apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif;}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* ---- topbar ---- */
.topbar{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:14px;
  background:var(--panel);border-bottom:1px solid var(--border);padding:10px 20px;flex-wrap:wrap}
.topbar .title{font-weight:700;font-size:16px}
.topbar .sub{color:var(--muted);font-size:12.5px}
.topbar .grow{flex:1}
.searchbox{display:flex;align-items:center;gap:8px}
#search{width:230px;padding:6px 10px;border:1px solid var(--border);border-radius:8px;font-size:13px;outline:none}
#search:focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
#search-status{font-size:12px;color:var(--muted);min-width:64px}
.btn{padding:6px 12px;border:1px solid var(--border);border-radius:8px;background:var(--panel);
  font-size:13px;cursor:pointer;color:var(--ink)}
.btn:hover{border-color:var(--accent);color:var(--accent)}

/* ---- sidebar ---- */
aside.toc{position:fixed;top:53px;left:0;bottom:0;width:300px;overflow-y:auto;
  background:var(--panel);border-right:1px solid var(--border);padding:14px 12px 40px}
.toc .toc-h{font-size:12px;color:var(--muted);letter-spacing:.12em;margin:10px 8px 4px}
.toc a.toc-doc{display:flex;justify-content:space-between;align-items:center;gap:6px;
  padding:6px 8px;border-radius:7px;font-weight:600;font-size:13.5px;color:var(--ink)}
.toc a.toc-doc:hover{background:var(--accent-soft);text-decoration:none}
.toc a.toc-doc.active{background:var(--accent-soft);color:var(--accent)}
.toc .toc-sub{margin:0 0 6px 14px;border-left:1px solid var(--border);padding-left:6px}
.toc .toc-sub a{display:block;padding:3px 8px;font-size:12.5px;color:var(--muted);
  border-radius:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.toc .toc-sub a:hover{color:var(--accent);text-decoration:none}
.match-count{background:#ffe58f;color:#5c4a00;border-radius:9px;font-size:11px;padding:0 7px}

/* ---- main ---- */
main{margin-left:300px;padding:28px 36px 90px;max-width:1040px}
.doc{background:var(--panel);border:1px solid var(--border);border-radius:12px;
  padding:34px 44px 40px;margin-bottom:26px}
.doc.hidden{display:none}
.doc .src{color:var(--muted);font-size:12px;margin:-6px 0 18px;font-family:ui-monospace,Consolas,monospace}
h1{font-size:25px;line-height:1.4;margin:0 0 6px;padding-bottom:12px;border-bottom:2px solid var(--border)}
h2{font-size:19px;margin:1.9em 0 .7em;padding-bottom:.28em;border-bottom:1px solid var(--border)}
h3{font-size:16.5px;margin:1.5em 0 .5em}
h4{font-size:15px;margin:1.2em 0 .4em}
p{margin:.75em 0}
.tbl{overflow-x:auto;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13.2px;line-height:1.65}
th,td{border:1px solid var(--border);padding:7px 11px;text-align:left;vertical-align:top}
th{background:#f0f2f5;white-space:nowrap}
tbody tr:nth-child(even){background:#fafbfc}
pre.code{background:var(--code-bg);border:1px solid var(--border);border-radius:9px;
  padding:13px 16px;overflow:auto;font:12.8px/1.55 ui-monospace,Consolas,"Courier New",monospace}
pre.code code{background:none;padding:0;font-size:inherit}
code{font-family:ui-monospace,Consolas,monospace;font-size:.9em;background:var(--code-bg);
  padding:1px 5px;border-radius:4px}
blockquote{margin:12px 0;padding:9px 16px;border-left:4px solid var(--accent);
  background:var(--accent-soft);border-radius:0 8px 8px 0}
blockquote p{margin:0}
hr{border:none;border-top:1px solid var(--border);margin:22px 0}
mark{background:#ffe58f;padding:0 2px;border-radius:3px}
ul,ol{padding-left:1.5em}
li{margin:.3em 0}

/* ---- review panel ---- */
.review-panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:26px 44px 30px;margin-bottom:26px}
.review-panel h1{border-bottom:none;margin-bottom:0}
.req-table td.center{text-align:center}
.req-table input[type=checkbox]{width:17px;height:17px;accent-color:var(--accent);cursor:pointer}
.hint{color:var(--muted);font-size:13px}
.meta-row{display:flex;gap:18px;flex-wrap:wrap;margin:10px 0 4px}
.meta-row label{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px}
.meta-row input{border:1px solid var(--border);border-radius:7px;padding:5px 9px;font-size:13px}
#verdict{width:100%;min-height:70px;margin-top:6px;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font:14px/1.6 inherit}
#save-tip{color:#0a7d33;font-size:12px;margin-left:8px;visibility:hidden}

#toTop{position:fixed;right:26px;bottom:26px;width:40px;height:40px;border-radius:50%;
  border:1px solid var(--border);background:var(--panel);cursor:pointer;font-size:16px;color:var(--muted);
  box-shadow:0 2px 8px rgba(0,0,0,.08);z-index:70}
#toTop:hover{color:var(--accent);border-color:var(--accent)}

@media (max-width:1020px){
  aside.toc{display:none}
  main{margin-left:0;padding:20px 16px 70px}
  .doc,.review-panel{padding:22px 18px}
}
@media print{
  .topbar,aside.toc,#toTop{display:none!important}
  main{margin:0;padding:0;max-width:none}
  body{background:#fff}
  .doc{border:none;border-radius:0;padding:0 0 20px;page-break-before:always}
  .doc:first-of-type{page-break-before:avoid}
  .review-panel{border:none;padding:0}
  a{color:inherit}
}
</style>
</head>
<body>

<header class="topbar">
  <span class="title">AgentPM 方案设计 · 评审版 v0.4</span>
  <span class="sub">__GENERATED__ · 含评审意见修订</span>
  <span class="grow"></span>
  <span class="searchbox">
    <input id="search" type="search" placeholder="全文搜索…（≥2 字符）">
    <span id="search-status"></span>
  </span>
  <button class="btn" id="print-btn">打印 / 导出 PDF</button>
</header>

<aside class="toc" id="toc">
  <div class="toc-h">评审导航</div>
  <a class="toc-doc" href="#review-top">需求对照表（勾选）</a>
  <div class="toc-h">方案文档</div>
  <!--TOC-->
</aside>

<main>
  <section class="review-panel" id="review-top">
    <h1>评审对照表</h1>
    <p class="hint">逐条核对原始需求与方案落点；勾选状态、评审人与意见自动保存在本机浏览器（localStorage），
    可随时关闭页面后继续。左侧边栏可跳转任意章节，右上搜索框支持全文检索，"打印 / 导出 PDF"输出纸质评审版。</p>
    <div class="tbl"><table class="req-table">
      <thead><tr><th>需求</th><th>要求摘要</th><th>方案落点（章节）</th><th style="text-align:center">评审通过</th></tr></thead>
      <tbody>
        <!--REQROWS-->
      </tbody>
    </table></div>
    <div class="meta-row">
      <label>评审人 <input id="reviewer" placeholder="姓名"></label>
      <label>日期 <input id="review-date" placeholder="YYYY-MM-DD"></label>
      <span id="save-tip">已保存 ✓</span>
    </div>
    <label class="hint" for="verdict">总体意见 / 遗留问题：</label>
    <textarea id="verdict" placeholder="记录评审结论、需修改项、责任人…"></textarea>
  </section>

  <!--BODY-->
</main>

<button id="toTop" title="返回顶部">↑</button>

<script>
/* ---------- persistence ---------- */
var tipTimer = null;
function flashSaved(){
  document.getElementById('save-tip').style.visibility = 'visible';
  clearTimeout(tipTimer);
  tipTimer = setTimeout(function(){ document.getElementById('save-tip').style.visibility = 'hidden'; }, 1500);
}
function bindPersist(id){
  var el = document.getElementById(id);
  if(!el) return;
  el.value = localStorage.getItem('apm-'+id) || '';
  el.addEventListener('input', function(){
    localStorage.setItem('apm-'+id, el.value); flashSaved();
  });
}
document.querySelectorAll('input[data-req]').forEach(function(cb){
  cb.checked = localStorage.getItem('apm-req-'+cb.dataset.req) === '1';
  cb.addEventListener('change', function(){
    localStorage.setItem('apm-req-'+cb.dataset.req, cb.checked ? '1' : '0'); flashSaved();
  });
});
['reviewer','review-date','verdict'].forEach(bindPersist);

/* ---------- print ---------- */
document.getElementById('print-btn').addEventListener('click', function(){ window.print(); });
document.getElementById('toTop').addEventListener('click', function(){
  window.scrollTo({top:0, behavior:'smooth'});
});

/* ---------- full-text search ---------- */
var searchInput = document.getElementById('search');
var searchStatus = document.getElementById('search-status');
function clearHighlights(){
  document.querySelectorAll('mark[data-hl]').forEach(function(m){
    var p = m.parentNode;
    m.replaceWith(document.createTextNode(m.textContent));
    p.normalize();
  });
  document.querySelectorAll('.doc').forEach(function(s){ s.classList.remove('hidden'); });
  document.querySelectorAll('.match-count').forEach(function(e){ e.textContent = ''; });
  searchStatus.textContent = '';
}
searchInput.addEventListener('input', function(){
  clearHighlights();
  var q = searchInput.value.trim().toLowerCase();
  if(q.length < 2) return;
  var total = 0;
  document.querySelectorAll('section.doc').forEach(function(sec){
    var count = 0;
    var walker = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT, {
      acceptNode: function(n){
        if(!n.textContent.trim()) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], cur;
    while((cur = walker.nextNode())) nodes.push(cur);
    nodes.forEach(function(node){
      var text = node.textContent, lower = text.toLowerCase();
      var idx = lower.indexOf(q);
      if(idx === -1) return;
      var frag = document.createDocumentFragment(), pos = 0, hits = 0;
      while(idx !== -1 && hits < 30){
        frag.appendChild(document.createTextNode(text.slice(pos, idx)));
        var mk = document.createElement('mark');
        mk.dataset.hl = '1'; mk.textContent = text.substr(idx, q.length);
        frag.appendChild(mk);
        pos = idx + q.length; hits++; count++;
        idx = lower.indexOf(q, pos);
      }
      frag.appendChild(document.createTextNode(text.slice(pos)));
      node.replaceWith(frag);
    });
    total += count;
    var badge = document.querySelector('.match-count[data-doc="'+sec.dataset.doc+'"]');
    if(badge && count) badge.textContent = count + ' 处';
    if(!count) sec.classList.add('hidden');
  });
  searchStatus.textContent = total ? total + ' 处匹配' : '无匹配';
});
document.querySelectorAll('.toc a').forEach(function(a){
  a.addEventListener('click', function(){
    if(searchInput.value){ searchInput.value = ''; clearHighlights(); }
  });
});

/* ---------- scrollspy ---------- */
var sections = [].slice.call(document.querySelectorAll('section.doc'));
var tocLinks = [].slice.call(document.querySelectorAll('a.toc-doc'));
window.addEventListener('scroll', function(){
  var y = window.scrollY + 90, active = null;
  sections.forEach(function(s){ if(!s.classList.contains('hidden') && s.offsetTop <= y) active = s; });
  tocLinks.forEach(function(a){ a.classList.toggle('active', active && a.getAttribute('href') === '#'+active.id); });
}, {passive:true});
</script>
</body>
</html>
"""


def build():
    body_parts = []
    toc_parts = []
    for path, key, nav_title in DOCS:
        raw = (ROOT / path).read_text(encoding="utf-8")
        conv = Converter(key, DOCS)
        rendered = conv.convert(raw)
        body_parts.append(
            f'<section class="doc" id="doc-{key}" data-doc="{key}">\n'
            f'<p class="src">来源文件：{html.escape(path)}</p>\n{rendered}\n</section>'
        )
        subs = "".join(
            f'<a href="#{hid}">{html.escape(text)}</a>'
            for level, text, hid in conv.headings
            if level == 2
        )
        toc_parts.append(
            f'<a class="toc-doc" href="#doc-{key}">{key} · {html.escape(nav_title)}'
            f'<span class="match-count" data-doc="{key}"></span></a>'
            + (f'<div class="toc-sub">{subs}</div>' if subs else "")
        )

    req_rows = "".join(
        f'<tr><td><strong>{name}</strong></td><td>{desc}</td>'
        f'<td><a href="#doc-{key.split(" ")[0]}">{docs_ref}</a></td>'
        f'<td class="center"><input type="checkbox" data-req="{rid}" title="勾选表示该需求评审通过"></td></tr>'
        for rid, name, desc, docs_ref, key in [
            (r[0], r[1], r[2], r[3], r[3]) for r in REQUIREMENT_ROWS
        ]
    )

    page = (
        TEMPLATE.replace("<!--TOC-->", "\n".join(toc_parts))
        .replace("<!--BODY-->", "\n".join(body_parts))
        .replace("<!--REQROWS-->", req_rows)
        .replace("__GENERATED__", f"v0.4 · 生成于 {date.today().isoformat()}")
    )
    out = ROOT / "review.html"
    out.write_text(page, encoding="utf-8")
    print(f"OK  wrote {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build()
