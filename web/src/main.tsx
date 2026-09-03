import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// PWA service worker（I48）：autoUpdate——新版本后台下载后自动接管，下次加载即新版；
// onNeedRefresh 在新 SW 就绪等待接管时触发，给出「立即刷新」提示。
// /api 永不入缓存（vite.config workbox.navigateFallbackDenylist + 无 runtimeCaching）。
registerSW({
  onNeedRefresh() {
    toast.info("已发布新版本", {
      description: "点击「刷新」立即更新；不刷新则下次打开自动生效",
      action: { label: "刷新", onClick: () => location.reload() },
      duration: Infinity,
    });
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      {/* sonner 全局挂载——此前缺失，所有 toast.* 均静默无显示（I48 顺手修复） */}
      <Toaster position="top-center" richColors />
    </QueryClientProvider>
  </React.StrictMode>,
);
