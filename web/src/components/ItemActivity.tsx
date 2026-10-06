/** M115-I344 工作项活动流（docs/01 §DF，Linear 吸纳轮）——事件溯源红利：
 * 审计流以工作项为中心的读面。数据 = /events?agg_type=item&agg_id=（M114-I339
 * 成员门），item.updated 的 `_old` 旧值（I344）渲染「从 A 改为 B」。
 * 组件保持纯展示：标题/状态名解析由调用方注入（看板已有全量上下文）。 */
import { useQuery } from "@tanstack/react-query";
import { api, type AEvent } from "../lib/api";

const PRIO: Record<string, string> = { high: "高", medium: "中", low: "低" };
const REL: Record<string, string> = {
  contains: "包含", depends_on: "依赖", produces: "产出", consumes: "消耗",
  blocks: "阻塞", precedes: "先于", relates: "关联",
  duplicates: "重复", includes: "包括",
};

export type ItemActivityResolvers = {
  statusName?: (sid: string) => string;
  titleOf?: (id: string) => string;
  userName?: (id: string) => string;
};

function fmtDate(v: unknown): string {
  return typeof v === "string" ? v.slice(0, 10) : String(v);
}

function fmtTs(ts: string): string {
  return ts.replace("T", " ").slice(0, 16);
}

/** One event → one human sentence (Linear activity 的克制口径：只讲变更)。 */
export function describeActivity(e: AEvent, r: ItemActivityResolvers): { icon: string; text: string } {
  const p = e.payload ?? {};
  const old = (p._old ?? {}) as Record<string, unknown>;
  const statusName = r.statusName ?? ((s: string) => s);
  const titleOf = r.titleOf ?? ((id: string) => String(id));
  const prio = (v: unknown) => PRIO[String(v)] ?? String(v ?? "（无）");
  switch (e.event_type) {
    case "item.created":
      return { icon: "✚", text: "创建工作项" };
    case "item.status_changed": {
      const from = p.from ? `由「${statusName(String(p.from))}」` : "";
      return { icon: "⇢", text: `状态${from}改为「${statusName(String(p.status))}」` };
    }
    case "item.assigned": {
      const userName = r.userName ?? ((id: string) => id);
      const to = p.assignee_id ? userName(String(p.assignee_id)) : "（未指派）";
      const from = p.from_assignee_id ? `（原：${userName(String(p.from_assignee_id))}）` : "";
      return { icon: "👤", text: `指派给 ${to}${from}` };
    }
    case "item.updated": {
      const bits: string[] = [];
      if ("title" in p) bits.push(`标题改为「${String(p.title)}」`);
      if ("description" in p) bits.push(old.description ? "更新了描述" : "补充了描述");
      if ("priority" in p) {
        bits.push(old.priority !== undefined && old.priority !== null
          ? `优先级 ${prio(old.priority)} → ${prio(p.priority)}`
          : `优先级设为 ${prio(p.priority)}`);
      }
      if ("estimate_hours" in p) bits.push(`估时改为 ${String(p.estimate_hours ?? "（无）")}h`);
      if ("start_date" in p) bits.push(`开始日改为 ${p.start_date ? fmtDate(p.start_date) : "（无）"}`);
      if ("due_date" in p) bits.push(`截止日改为 ${p.due_date ? fmtDate(p.due_date) : "（无）"}`);
      if ("cycle_id" in p) bits.push(p.cycle_id ? `挂入周期 ${titleOf(String(p.cycle_id))}` : "移出周期");
      if ("milestone_id" in p) bits.push(p.milestone_id ? `关联里程碑 ${titleOf(String(p.milestone_id))}` : "移除里程碑");
      if ("parent_id" in p) bits.push(p.parent_id ? `挂到父项 ${titleOf(String(p.parent_id))}` : "调整为顶层");
      if ("feature_id" in p) bits.push(p.feature_id ? `归入功能 ${titleOf(String(p.feature_id))}` : "移出功能");
      if ("auto_scheduled" in p) bits.push(Number(p.auto_scheduled) ? "开启自动排期" : "改为手动排期");
      if ("recurrence_days" in p) bits.push(p.recurrence_days ? `完成后 ${String(p.recurrence_days)} 天自动重建` : "关闭自动重建");
      if ("custom_fields" in p) bits.push("更新了自定义字段");
      if ("labels" in p) {
        const n = Array.isArray(p.labels) ? p.labels.length : 0;
        const had = Array.isArray(old.labels) ? (old.labels as unknown[]).length : null;
        bits.push(had === null
          ? (n > 0 ? `打了 ${n} 个标签` : "移除了全部标签")
          : `标签 ${had ?? 0} → ${n}`);
      }
      return { icon: "✎", text: bits.length ? bits.join("，") : "更新了属性" };
    }
    case "item.rescheduled":
      return { icon: "⟲", text: `自动顺期至 ${p.due_date ? fmtDate(p.due_date) : "（无）"}` };
    case "item.related":
      return { icon: "⛓", text: `建立「${REL[String(p.relation_type)] ?? String(p.relation_type)}」关系 → ${titleOf(String(p.to_item))}` };
    case "item.relation_removed":
      return { icon: "⛓", text: `解除「${REL[String(p.relation_type)] ?? String(p.relation_type)}」关系 → ${titleOf(String(p.to_item))}` };
    case "item.checklist_updated":
      return { icon: "☑", text: "更新了清单" };
    case "item.checklist_extracted":
      return { icon: "☑", text: "清单项转为任务" };
    case "item.archived":
      return { icon: "🗄", text: "移入归档" };
    case "item.restored":
      return { icon: "↩", text: "从归档恢复" };
    default:
      return { icon: "·", text: e.event_type };
  }
}

export function ItemActivity({ itemId, resolvers = {} }: {
  itemId: string;
  resolvers?: ItemActivityResolvers;
}) {
  const q = useQuery({
    queryKey: ["item-activity", itemId],
    queryFn: () => api.listEvents({ agg_type: "item", agg_id: itemId, limit: 60 }),
  });
  const evts = [...(q.data?.events ?? [])].sort((a, b) => b.id - a.id);
  if (q.isLoading) {
    return <p className="px-1 py-2 text-[10px] text-mut">加载活动…</p>;
  }
  if (q.isError) {
    return <p className="px-1 py-2 text-[10px] text-mut">活动加载失败</p>;
  }
  if (!evts.length) {
    return <p className="px-1 py-2 text-[10px] text-mut">暂无活动记录</p>;
  }
  return (
    <ol className="space-y-1.5 px-1 py-2" aria-label="工作项活动流">
      {evts.map((e) => {
        const { icon, text } = describeActivity(e, resolvers);
        return (
          <li key={e.id} className="flex items-baseline gap-1.5 text-[11px] leading-4">
            <span aria-hidden className="shrink-0 text-mut">{icon}</span>
            <span className="min-w-0 flex-1 break-all text-ink">
              {text}
              {e.event_type === "comment.created" && (
                <span className="text-mut">（见评论页签）</span>
              )}
            </span>
            <span className="shrink-0 text-[10px] text-mut">
              {e.actor_type === "user" ? (e.actor_name ?? e.actor_id) : e.actor_type === "agent" ? `🤖 ${e.actor_id}` : e.actor_type}
              <span aria-hidden> · </span>
              {fmtTs(e.ts)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
