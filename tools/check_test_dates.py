"""测试日期稳健性对账（M84-I253，docs/01 §CC.3）——check_write_gates 台账模式
的第四次机械防腐：测试代码里的硬编码 ISO 日期本身无害（实体属性/合成时钟），
**有害的是它流进按真实时钟开窗的端点**（smoke_26 教训：硬编码 spent_on 跨午夜
滑出 /my/timelog 28 天窗→KeyError 假红，M45 教训第三例）。

启发式：文件**同时含**硬编码日期字面量与窗口端点引用 → 必须在 REVIEWED 台账
登记人工定类（三分类+理由）；未登记即非零退出。窗口端点名册（SQL 含
`spent_on >=`/`week_start` 等真实时钟窗口，逐个读过实现）：
  /my/timelog（默认 28d）、/workload（7d+周桶）、health/history（30d）、
  forecast（完整历史周）、/my/work（本周 ISO 周）。
台账外新文件红=逼一次有意识的分类（密闭①/静态锚②/真窗炸弹③），而不是等
跨午夜假红。三分类判据与既有锚定范式见 docs/01 §CC.1。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 真实时钟窗口端点（子串匹配测试源码中的 URL 字面量）
WINDOWED_ENDPOINTS: dict[str, str] = {
    "my/timelog": "/my/timelog（默认 28 天窗·timelog.py spent_on >= today-N）",
    "workload": "/workload（7 天+跨周桶·reports.py week_ago）",
    "health/history": "/health/history（默认 30 天采样·reports.py _now）",
    "forecast": "/forecast（只认完全落入历史的完整周·M45 原发教训）",
    "my/work": "/my/work（本周 ISO 周 minutes·reports.py week_start）",
}

DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}")

# REVIEWED 台账：相对路径 → （分类，理由）——被扫描器点名（日期字面量×窗口端点
# 引用交集）后的**人工裁决记录**，因此只含交集文件；无窗口端点引用的含日期文件
# （合成时钟①/纯静态锚②）扫描器本就不会点名，无需登记。分类：①密闭合成时钟
# ②静态实体锚 ③真窗炸弹（须动态锚定——台账内不应出现③未修状态）。
REVIEWED: dict[str, tuple[str, str]] = {
    "app/tests/test_timelog.py": (
        "①+②", "/my/timelog 与 /my/work 的窗口断言全部用 today/yesterday 与 UTC 锚"
        "（M38 审阅修·137-141 行注释在岗）；_log 默认日期已动态化（M84-I252 加固——"
        "原硬编码 2026-09-04 只喂 item 级无窗聚合，防未来误接窗口端点）"),
    "app/tests/test_reports.py": (
        "②", "spent_on=2026-09-05 只喂 portfolio/report（SUM 无时间窗）；"
        "due=2026-01-01 为 overdue 静态过去锚；/my/work 断言只看结构不看日期"
        "（M84-I252 定类）"),
    "app/tests/test_health_history.py": (
        "②", "health/history 30 天窗但 past=2026-01-01 只作 overdue 静态过去锚；"
        "series 断言用真实 today 样点（M84-I252 定类）"),
    "app/tests/test_archive_semantics.py": (
        "②", "health/history 7 天窗但 due=2026-01-01 只作 overdue 静态过去锚"
        "（断言对象=归档排除而非窗口成员资格·任何运行日 2026-01-01 恒为过去；"
        "归档事件发生在 now，天然在窗内。M118-I361 定类）"),
    "app/tests/smoke/test_smoke_26_m20_experience.py": (
        "③已修", "/my/timelog 窗口断言已动态锚定 date.today()-3/-2"
        "（M83-I251 发现即修——本轮防的正是这个炸弹的原型）"),
    "app/tests/smoke/test_smoke_58_m53_html_digest_resource.py": (
        "①+②", "workload 周桶日期锚服务端 UTC 时钟（reports._now·M63-I191 修复在岗）；"
        "due=2026-01-05 为 estimate 静态实体锚；机检首日抓获的人工对账漏网（M84-I253 自证）"),
    "app/tests/smoke/test_smoke_89_m84_test_dates.py": (
        "①", "本冒烟自证的哨兵字符串含硬编码日期（故意红自证载体·非真实测试语义）"),
}


def scan() -> list[tuple[str, list[str]]]:
    """含日期字面量×窗口端点引用、但未登记台账的文件清单。"""
    out: list[tuple[str, list[str]]] = []
    tests_dir = ROOT / "app" / "tests"
    for py in sorted(tests_dir.rglob("*.py")):
        src = py.read_text(encoding="utf-8", errors="replace")
        if not DATE_RE.search(src):
            continue
        hits = [ep for ep in WINDOWED_ENDPOINTS if ep in src]
        if not hits:
            continue
        rel = py.relative_to(ROOT).as_posix()
        if rel in REVIEWED:
            continue
        out.append((rel, hits))
    return out


def main() -> int:
    findings = scan()
    if findings:
        print("测试日期稳健性对账 ✗ —— 以下文件含硬编码日期×窗口端点引用，未登记台账：")
        for rel, hits in findings:
            print(f"  {rel}  →  {', '.join(hits)}")
        print("请在 tools/check_test_dates.py REVIEWED 台账登记三分类+理由"
              "（①密闭合成时钟 ②静态实体锚 ③真窗炸弹→动态锚定后登记③已修）。")
        return 1
    print(f"测试日期稳健性对账 ✓（台账 {len(REVIEWED)} 文件·窗口端点名册 "
          f"{len(WINDOWED_ENDPOINTS)} 端点）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
