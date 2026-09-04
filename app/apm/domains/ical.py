"""iCal calendar subscription (M21-I66, docs/01 §T.3): the key owner's own
schedule as all-day VEVENTs — assigned active items (due-anchored, start-span
when both dates exist) plus milestone deadlines of visible projects. Any
calendar client can subscribe via the personal URL (OpenProject 13.0 pattern;
Redmine core still lacks ICS feeds, #1077). Reuses the M11 feed_key (rotate →
old key 401); hand-written RFC 5545 text, zero new dependencies."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response

from apm.core import db
from apm.domains.feed import _user_by_feed_key, _visible

router = APIRouter(tags=["ical"])


def _esc(s: str) -> str:
    """RFC 5545 TEXT escaping (backslash first)."""
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def _basic(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _day_plus1(iso_date: str) -> str:
    d = date.fromisoformat(iso_date) + timedelta(days=1)  # DTEND is exclusive
    return d.strftime("%Y%m%d")


def _fold(line: str) -> list[str]:
    """Rough content-line folding at 74 chars (char-level; clients tolerate)."""
    if len(line) <= 74:
        return [line]
    out, first = [], True
    while line:
        out.append(line if first else " " + line)
        line = line[74 if first else 73:]
        first = False
    return out


@router.get("/my/calendar.ics")
def my_calendar(key: str, response: Response) -> Response:
    user = _user_by_feed_key(key)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid feed key")
    me = user["id"]
    conn = db.get_conn()
    now = _basic(datetime.now(timezone.utc))

    items = conn.execute(
        "SELECT i.id, i.title, i.status, i.start_date, i.due_date, i.updated_at,"
        " p.name AS project_name FROM items i"
        " JOIN projects p ON p.id = i.project_id"
        " WHERE i.assignee_type = 'human' AND i.assignee_id = ?"
        " AND i.status_group NOT IN ('done','cancelled')"
        " AND (i.due_date IS NOT NULL OR i.start_date IS NOT NULL)"
        " ORDER BY i.due_date, i.id",
        (me,),
    ).fetchall()

    milestones = []
    for m in conn.execute(
        "SELECT m.id, m.title, m.due_date, m.project_id, p.name AS project_name"
        " FROM milestones m JOIN projects p ON p.id = m.project_id"
        " ORDER BY m.due_date, m.id",
    ).fetchall():
        if _visible(m["project_id"], user):
            milestones.append(m)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AgentPM//My Schedule//CN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:AgentPM · 我的日程",
    ]
    for it in items:
        anchor = it["due_date"] or it["start_date"]
        dtstart = (it["start_date"] or it["due_date"]).replace("-", "")
        summary = _esc(f"[{it['status']}] {it['title']} · {it['project_name']}")
        updated = it["updated_at"]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it['id']}@agentpm",
            f"DTSTAMP:{_basic(datetime.fromisoformat(updated)) if updated else now}",
            f"SUMMARY:{summary}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{_day_plus1(anchor)}",
            f"DESCRIPTION:{_esc('工作项 %s（%s）' % (it['id'], it['project_name']))}",
            "END:VEVENT",
        ]
    for m in milestones:
        summary = _esc(f"◆ {m['title']}（里程碑截止 · {m['project_name']}）")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{m['id']}@agentpm",
            f"DTSTAMP:{now}",
            f"SUMMARY:{summary}",
            f"DTSTART;VALUE=DATE:{m['due_date'].replace('-', '')}",
            f"DTEND;VALUE=DATE:{_day_plus1(m['due_date'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    body = "\r\n".join(folded) + "\r\n"
    return Response(content=body, media_type="text/calendar; charset=utf-8")
