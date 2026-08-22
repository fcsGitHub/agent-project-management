import { useQuery } from "@tanstack/react-query";

type Health = { status: string; version: string; provider_mode: string };

export default function App() {
  const { data, isLoading } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: async () => {
      const r = await fetch("/api/health");
      if (!r.ok) throw new Error(`health ${r.status}`);
      return r.json();
    },
  });

  return (
    <div className="flex h-full items-center justify-center">
      <div className="rounded-[12px] border border-line bg-surface p-8 text-center shadow-sm">
        <div className="text-lg font-semibold">AgentPM</div>
        <p className="mt-2 text-sm text-mut">
          {isLoading
            ? "正在连接后端…"
            : data
              ? `后端就绪 · ${data.version} · provider=${data.provider_mode}`
              : "后端不可用——请先启动 API（uvicorn apm.main:app）"}
        </p>
        <p className="mt-4 text-xs text-mut">前端骨架（I0）· 页面将在后续迭代装配</p>
      </div>
    </div>
  );
}
