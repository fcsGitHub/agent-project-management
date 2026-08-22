#!/usr/bin/env python
"""Seed demo data (replay mode): a full project lifecycle with assets.

Usage: python tools/seed.py [--api http://localhost:8000]
Safe to re-run: creates a fresh project each time.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

BASE = "http://localhost:8000"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def wait_status(path: str, statuses: tuple[str, ...], timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        obj = call("GET", path)
        if obj.get("status") in statuses:
            return obj
        time.sleep(0.2)
    raise TimeoutError(f"{path} stuck at {obj.get('status')}")


def pending_gate(project_id: str, gate: str | None = None) -> dict:
    approvals = call("GET", f"/api/approvals?status=pending&project_id={project_id}")["approvals"]
    for a in approvals:
        if gate is None or a["payload_snapshot"].get("gate") == gate:
            return a
    raise LookupError(f"no pending approval gate={gate}")


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=BASE)
    args = ap.parse_args()
    BASE = args.api

    health = call("GET", "/api/health")
    print(f"· backend: {health['status']} (provider={health['provider_mode']})")

    # Project A: full software-dev flow
    a = call("POST", "/api/projects", {
        "name": "周报工具（演示）", "ontology": "software-dev",
        "requirement": "汇总 Git 提交与任务状态，自动生成周报",
    })
    pid = a["id"]
    conv = a["bootstrap"]["conversation_id"]
    print(f"· project A: {pid}")

    run = call("POST", "/api/runs", {"conversation_id": conv, "agent_role": "pm-agent"})
    wait_status(f"/api/runs/{run['id']}", ("interrupted",))
    call("POST", f"/api/conversations/{conv}/messages",
         {"content": "必须兼容 Python 3.9，不要用 3.10+ 语法"})
    call("POST", f"/api/conversations/{conv}/resume", {"instruction": "按补充约束重拟 PRD"})
    wait_status(f"/api/runs/{run['id']}", ("interrupted",))
    call("POST", f"/api/approvals/{pending_gate(pid, 'prd_review')['id']}/decision",
         {"decision": "approved", "comment": "OK，约束已纳入"})
    wait_status(f"/api/runs/{run['id']}", ("succeeded", "failed"))
    print("· PRD approved (with injected constraint)")

    plan_conv = None
    for _ in range(50):
        convs = call("GET", f"/api/conversations?project_id={pid}")["conversations"]
        plan_conv = next((c for c in convs if c["title"] == "计划确认"), None)
        if plan_conv:
            break
        time.sleep(0.2)
    plan_runs = call("GET", f"/api/runs?conversation_id={plan_conv['id']}")["runs"]
    wait_status(f"/api/runs/{plan_runs[0]['id']}", ("interrupted",))
    call("POST", f"/api/approvals/{pending_gate(pid, 'plan_review')['id']}/decision",
         {"decision": "approved"})
    wait_status(f"/api/runs/{plan_runs[0]['id']}", ("succeeded", "failed"))
    items = call("GET", f"/api/projects/{pid}/items")["items"]
    print(f"· plan approved → {len(items)} tasks")

    for i in items:
        call("PATCH", f"/api/items/{i['id']}",
             {"assignee_type": "agent", "assignee_id": "dev-agent"})
    started = call("POST", "/api/orchestrator/batch-start",
                   {"item_ids": [items[0]["id"]]})["started"][0]
    wait_status(f"/api/runs/{started['run_id']}", ("interrupted",))
    call("POST", f"/api/conversations/{started['conversation_id']}/messages",
         {"content": "第 3 步的异常处理改成重试三次"})
    call("POST", f"/api/conversations/{started['conversation_id']}/resume",
         {"instruction": "按纠正指令重做"})
    wait_status(f"/api/runs/{started['run_id']}", ("interrupted",))
    call("POST", f"/api/approvals/{pending_gate(pid, 'code_review')['id']}/decision",
         {"decision": "approved"})
    wait_status(f"/api/runs/{started['run_id']}", ("succeeded", "failed"))
    print("· batch dev run interrupted/resumed/approved")

    # deposit a regression suite asset
    report = "# 登录回归套件 v3\n\n## 用例\n- 正确账号密码登录 ✅\n- 密码错误 5 次锁定 ✅\n"
    art = call("PUT", f"/api/projects/{pid}/artifacts/test/login-regression.md",
               {"content": report, "message": "qa: login regression"})
    asset = call("POST", "/api/assets", {
        "source_project_id": pid, "artifact_path": art["path"], "commit": art["commit"],
        "library": "test", "kind": "test-suite", "title": "登录回归套件", "tags": ["登录", "回归"],
    })
    rev = call("POST", f"/api/assets/{asset['id']}/submit_review")
    call("POST", f"/api/approvals/{rev['approval_id']}/decision", {"decision": "approved"})
    print("· asset published to test library")

    # Project B consumes it
    b = call("POST", "/api/projects", {
        "name": "轻量调研（演示）", "ontology": "generic", "requirement": "做一次竞品调研",
    })
    print(f"· project B (generic): {b['id']}")
    print("seed complete ✓  open the UI and try ⌘K（自然语言：只看高优先级任务）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
