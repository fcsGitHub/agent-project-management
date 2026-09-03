/** Small formatting helpers shared across pages. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return `${Math.floor(diff / 86_400_000)} 天前`;
}

export function clockOf(iso: string | null | undefined): string {
  if (!iso) return "--:--";
  return new Date(iso).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Renderable custom-field badges for an item, following its concept's field
 * declarations (M6-I21). Only declared fields with a present value are shown. */
export function customFieldBadges(
  item: { concept_id: string; custom_fields?: Record<string, unknown> | null },
  concepts?: { id: string; fields?: { id: string; name: string; type: string }[] }[],
): { label: string; text: string }[] {
  const concept = concepts?.find((c) => c.id === item.concept_id);
  const cf = item.custom_fields ?? {};
  const out: { label: string; text: string }[] = [];
  for (const f of concept?.fields ?? []) {
    const v = cf[f.id];
    if (v === undefined || v === null) continue;
    const text = Array.isArray(v)
      ? v.join("/")
      : typeof v === "boolean"
        ? v ? "是" : "否"
        : String(v);
    out.push({ label: f.name, text });
  }
  return out;
}
