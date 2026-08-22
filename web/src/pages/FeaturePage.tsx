/** Feature page: board slice / conversations / artifacts tabs + brief (L2) card. */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { timeAgo } from "../lib/fmt";
import {
  Badge, Button, Card, CONV_STATUS, Drawer, Empty, GROUP_NAME, GROUP_TONE, Modal,
  Tabs, Textarea, Input, cx,
} from "../components/ui";
import Markdown from "react-markdown";
import { useEffect } from "react";
import { toast } from "sonner";

export function FeaturePage() {
  const { pid, fid } = useParams();
  const [tab, setTab] = useState("board");
  const [briefOpen, setBriefOpen] = useState(false);
  const [newConv, setNewConv] = useState(false);
  const feature = useQuery({
    queryKey: ["feature", fid],
    queryFn: () => api.getFeature(fid!),
    enabled: !!fid,
  });

  if (!pid || !fid) return null;
  const f = feature.data;
  if (!f) return <div className="p-6 text-sm text-mut">加载功能…</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">{f.title}</span>
        <Button size="sm" variant="ghost" onClick={() => setBriefOpen(true)}>简报 L2 ✎</Button>
        <Button size="sm" variant="primary" className="ml-auto" onClick={() => setNewConv(true)}>＋ 对话</Button>
      </div>
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "board", label: "看板切片", count: f.items?.length },
          { id: "conversations", label: "对话", count: f.conversations?.length },
          { id: "artifacts", label: "工件", count: f.artifacts?.length },
        ]}
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "board" && <BoardSlice items={f.items ?? []} pid={pid} />}
        {tab === "conversations" && <ConversationList conversations={f.conversations ?? []} pid={pid} />}
        {tab === "artifacts" && <ArtifactList artifacts={f.artifacts ?? []} pid={pid} />}
      </div>

      <BriefDrawer open={briefOpen} onClose={() => setBriefOpen(false)} feature={f} />
      <NewConversationModal open={newConv} onClose={() => setNewConv(false)} pid={pid} fid={fid} />
    </div>
  );
}

function BoardSlice({ items, pid }: { items: import("../lib/api").Item[]; pid: string }) {
  const groups = ["backlog", "todo", "in_progress", "done", "cancelled"];
  if (!items.length)
    return <Empty icon="▦" title="暂无工作项" hint="批准计划后 Planner-Agent 会在此创建任务；也可从看板手动建卡" />;
  return (
    <div className="flex gap-3 overflow-x-auto">
      {groups.map((g) => {
        const list = items.filter((i) => i.status_group === g);
        if (!list.length) return null;
        return (
          <div key={g} className="w-60 shrink-0">
            <div className="mb-2 flex items-center gap-2">
              <Badge tone={GROUP_TONE[g]}>{GROUP_NAME[g]}</Badge>
              <span className="text-xs text-mut">{list.length}</span>
            </div>
            <div className="space-y-2">
              {list.map((i) => (
                <Link key={i.id} to={`/p/${pid}/board?feature=${i.feature_id ?? ""}`}>
                  <Card className="p-2.5 text-xs hover:border-acc">
                    <div className="truncate font-medium">{i.title}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Badge tone={GROUP_TONE[i.status_group]}>{i.status}</Badge>
                      {i.priority === "high" && <Badge tone="red">高优</Badge>}
                      {i.assignee_id && <Badge tone="violet">🤖 {i.assignee_id}</Badge>}
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ConversationList({ conversations, pid }: { conversations: import("../lib/api").Conversation[]; pid: string }) {
  if (!conversations.length)
    return <Empty icon="💬" title="暂无对话" hint="「＋ 对话」发起起草/执行/临时对话" />;
  const active = conversations.filter((c) => c.status !== "archived");
  return (
    <div className="space-y-2">
      {active.map((c) => {
        const s = CONV_STATUS[c.status] ?? { label: c.status, tone: "neutral" };
        return (
          <Link key={c.id} to={`/p/${pid}/c/${c.id}`}>
            <Card className="flex items-center gap-3 p-3 text-sm hover:border-acc">
              <span className="font-medium">{c.title ?? "对话"}</span>
              <Badge tone="indigo">
                {{ drafting: "起草", executing: "执行", reviewing: "评审", adhoc: "临时", ui_command: "操作" }[c.kind] ?? c.kind}
              </Badge>
              <Badge tone={s.tone}>{s.label}</Badge>
              <span className="ml-auto text-xs text-mut">{timeAgo(c.updated_at)}</span>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}

function ArtifactList({ artifacts, pid }: { artifacts: import("../lib/api").Artifact[]; pid: string }) {
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [deposit, setDeposit] = useState<import("../lib/api").Artifact | null>(null);
  const art = useQuery({
    queryKey: ["artifact", pid, openPath],
    queryFn: () => api.getArtifact(pid, openPath!),
    enabled: !!openPath,
  });
  if (!artifacts.length)
    return <Empty icon="📄" title="暂无工件" hint="Agent 起草 PRD/WBS 后会出现在这里" />;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        {artifacts.map((a) => (
          <Card key={a.path} className="cursor-pointer p-3 text-xs hover:border-acc" onClick={() => setOpenPath(a.path)}>
            <div className="truncate font-mono font-medium">{a.path.split("/").pop()}</div>
            <div className="mt-1 truncate text-mut">{a.path}</div>
            <div className="mt-2 flex items-center gap-1.5">
              <Badge tone="neutral">{a.versions} 版</Badge>
              {a.deposits_to && <Badge tone="green">可沉淀 → {a.deposits_to}</Badge>}
            </div>
          </Card>
        ))}
      </div>
      <Drawer open={!!openPath} onClose={() => setOpenPath(null)} title={openPath ?? ""} width="50%">
        {art.data && (
          <div className="space-y-3">
            <div className="prose prose-zinc prose-sm max-w-none text-ink">
              <Markdown>{art.data.content}</Markdown>
            </div>
            {art.data.diff_vs_previous && (
              <details>
                <summary className="cursor-pointer text-xs text-mut">diff vs 上一版</summary>
                <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-bg p-3 text-[11px]">
                  {art.data.diff_vs_previous}
                </pre>
              </details>
            )}
            <div className="text-xs text-mut">
              版本史：{art.data.history.map((h) => h.commit.slice(0, 7)).join(" ← ")}
            </div>
            {art.data.path.includes("test") || true ? (
              <Button variant="outline" onClick={() => setDeposit(artifacts.find((x) => x.path === openPath) ?? null)}>
                📚 沉淀为资产
              </Button>
            ) : null}
          </div>
        )}
      </Drawer>
      <DepositModal artifact={deposit} onClose={() => setDeposit(null)} pid={pid} />
    </>
  );
}

function BriefDrawer({ open, onClose, feature }: {
  open: boolean; onClose: () => void; feature: import("../lib/api").Feature;
}) {
  const qc = useQueryClient();
  const [text, setText] = useState(feature.brief ?? "");
  return (
    <Drawer open={open} onClose={onClose} title={`功能简报（L2）· ${feature.title}`}>
      <Textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-3 flex justify-end">
        <Button variant="primary" onClick={async () => {
          await api.patchFeature(feature.id, { brief: text });
          await qc.invalidateQueries({ queryKey: ["feature", feature.id] });
          onClose();
        }}>保存简报</Button>
      </div>
    </Drawer>
  );
}

function NewConversationModal({ open, onClose, pid, fid }: {
  open: boolean; onClose: () => void; pid: string; fid: string;
}) {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("adhoc");
  const [instruction, setInstruction] = useState("");
  const qc = useQueryClient();
  return (
    <Modal open={open} onClose={onClose} title="新对话">
      <div className="space-y-3">
        <Input placeholder="标题（如：PRD 讨论）" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="flex gap-1.5">
          {["drafting", "executing", "reviewing", "adhoc"].map((k) => (
            <button key={k} onClick={() => setKind(k)}
              className={cx("rounded-lg border px-2.5 py-1.5 text-xs",
                kind === k ? "border-acc bg-accbg text-acc" : "border-line text-mut")}>
              {{ drafting: "起草", executing: "执行", reviewing: "评审", adhoc: "临时" }[k]}
            </button>
          ))}
        </div>
        <Textarea rows={3} placeholder="L3 会话指令（如：为登录模块起草 PRD）" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!title.trim()} onClick={async () => {
            const c = await api.createConversation({ project_id: pid, feature_id: fid, kind, title, instruction });
            await qc.invalidateQueries();
            onClose();
            navigate(`/p/${pid}/c/${c.id}`);
          }}>创建并打开</Button>
        </div>
      </div>
    </Modal>
  );
}


function DepositModal({ artifact, onClose, pid }: {
  artifact: import("../lib/api").Artifact | null; onClose: () => void; pid: string;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [library, setLibrary] = useState("test");
  const [kind, setKind] = useState("test-suite");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (artifact) { setTitle(artifact.path.split("/").pop()?.replace(/\./g, "-") ?? ""); } }, [artifact]);
  if (!artifact) return null;
  return (
    <Modal open={!!artifact} onClose={onClose} title="沉淀为资产（入库评审 Gate）">
      <div className="space-y-3">
        <div className="text-xs text-mut">来源工件：<span className="font-mono">{artifact.path}</span></div>
        <Input placeholder="资产标题（如：登录回归套件）" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="flex gap-2">
          {[["test", "🧪 测试库", "test-suite"], ["product", "📦 产品库", "prd-template"], ["doc", "📚 文档库", "adr"]].map(([lib, label, k]) => (
            <button key={lib} onClick={() => { setLibrary(lib); setKind(k); }}
              className={cx("flex-1 rounded-lg border px-3 py-2 text-xs",
                library === lib ? "border-acc bg-accbg text-acc" : "border-line text-mut")}>
              {label}
            </button>
          ))}
        </div>
        <div className="text-xs text-mut">kind：{kind}（由本体 assetKinds 校验）</div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!title.trim() || busy} onClick={async () => {
            setBusy(true);
            try {
              const r = await fetch("/api/assets", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source_project_id: pid, artifact_path: artifact.path, commit: artifact.commit, library, kind, title }),
              });
              const asset = await r.json();
              const rr = await fetch(`/api/assets/${asset.id}/submit_review`, { method: "POST" });
              const rev = await rr.json();
              toast.success("已提交入库评审", { description: `审批 ${rev.approval_id?.slice(0, 10)}… 待批准后发布` });
              await qc.invalidateQueries();
              onClose();
            } catch (e) {
              toast.error("沉淀失败", { description: String(e) });
            } finally {
              setBusy(false);
            }
          }}>提交入库评审</Button>
        </div>
      </div>
    </Modal>
  );
}
