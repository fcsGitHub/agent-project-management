"""Competency Question answerability check (M4-I16, docs/08 §8.1).

semantica 的 CQ 验收锚点落地：ontology YAML 顶层可选 `cq_mappings` 把每条
competencyQuestion 声明到支撑数据面（投影表/事件类型），cq-check 扫描实际数据量，
报告三态——answerable（可回答，有数据）/ no_data（缺数据，映射了但没数据）/
unmapped（缺映射，未声明支撑面）。证据摘要附计数与分布，人可判读。
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException

from apm.core import db
from apm.domains.ontology import CQ_SOURCES

router = APIRouter(tags=["ontology-cq"])


def _projects_using(name: str, conn) -> list[str]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM projects WHERE ontology = ?", (name,)).fetchall()]


def _evidence(support: dict, pids: list[str], conn) -> dict:
    source = support["source"]
    ph = ",".join("?" for _ in pids) or "''"
    count, summary = 0, ""

    def dist(counter: Counter, unit: str) -> str:
        return " · ".join(f"{k}×{v}" for k, v in counter.most_common(4)) or f"0 {unit}"

    if source == "items":
        rows = conn.execute(
            f"SELECT concept_id, title FROM items WHERE project_id IN ({ph})", pids
        ).fetchall() if pids else []
        declared = support.get("concepts") or []
        if declared:
            rows = [r for r in rows if r["concept_id"] in declared]
        count = len(rows)
        summary = dist(Counter(r["concept_id"] or "?" for r in rows), "工作项")
        if rows:
            summary += f"（如「{rows[0]['title']}」）"
    elif source == "relations":
        rows = conn.execute(
            f"SELECT r.relation_type FROM item_relations r"
            f" WHERE r.project_id IN ({ph})", pids).fetchall() if pids else []
        declared = support.get("relation_types") or []
        if declared:
            rows = [r for r in rows if r["relation_type"] in declared]
        count = len(rows)
        summary = dist(Counter(r["relation_type"] for r in rows), "关系")
    elif source == "approvals":
        rows = conn.execute(
            f"SELECT kind, status FROM approvals WHERE project_id IN ({ph})", pids
        ).fetchall() if pids else []
        declared = support.get("kinds") or []
        if declared:
            rows = [r for r in rows if r["kind"] in declared]
        count = len(rows)
        summary = dist(Counter(r["kind"] for r in rows), "审批") + \
            "；状态 " + dist(Counter(r["status"] for r in rows), "")
    elif source == "assets":
        rows = conn.execute("SELECT kind, status FROM assets").fetchall()
        declared = support.get("kinds") or []
        if declared:
            rows = [r for r in rows if r["kind"] in declared]
        count = len(rows)
        summary = dist(Counter(r["kind"] for r in rows), "资产")
    elif source == "runs":
        rows = conn.execute(
            f"SELECT agent_role FROM runs WHERE project_id IN ({ph})", pids
        ).fetchall() if pids else []
        count = len(rows)
        summary = dist(Counter(r["agent_role"] or "?" for r in rows), "运行")
    elif source == "events":
        declared = support.get("event_types") or []
        per = {t: conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_type = ?", (t,)).fetchone()["n"]
            for t in declared}
        count = sum(per.values())
        summary = " · ".join(f"{t}×{n}" for t, n in per.items())
    elif source == "artifacts":
        from apm.content.artifacts import list_artifacts

        total, per_project = 0, 0
        for pid in pids:
            try:
                total += len(list_artifacts(pid))
                per_project += 1
            except Exception:  # 内容仓缺失等；证据扫描不抛错
                continue
        count = total
        summary = f"{total} 份工件（{per_project} 个项目）"
    return {"source": source, "count": count, "summary": summary}


@router.get("/ontologies/{name}/cq-check")
def cq_check(name: str) -> dict:
    from apm.domains.ontology import OntologyError, load_ontology
    from apm.domains.ontology_versions import _load_live

    try:
        onto = load_ontology(name)
    except OntologyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if onto.errors:
        raise HTTPException(status_code=422, detail=f"ontology '{name}' has validation errors")

    raw = _load_live(name)
    mappings = {m.get("question"): m for m in (raw.get("cq_mappings") or [])
                if isinstance(m, dict) and m.get("question")}

    conn = db.get_conn()
    pids = _projects_using(name, conn)
    questions = []
    for q in onto.competency_questions:
        m = mappings.get(q)
        if not m:
            questions.append({"question": q, "status": "unmapped", "evidence": []})
            continue
        evidence = [_evidence(s, pids, conn) for s in m.get("supports", [])]
        status = "answerable" if any(e["count"] > 0 for e in evidence) else "no_data"
        questions.append({"question": q, "status": status, "evidence": evidence})

    by = Counter(q["status"] for q in questions)
    summary = (f"可回答 {by.get('answerable', 0)} · 缺数据 {by.get('no_data', 0)}"
               f" · 缺映射 {by.get('unmapped', 0)}")
    return {"name": name, "checked": len(questions), "questions": questions, "summary": summary}
