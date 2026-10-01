/** 渲染层错误边界（M82-I246）：React 只允许 class 组件充当边界，且只捕获子树渲染错误
 * （事件处理器/异步回调不归它管——数据层网络错误由 M45 的 fetch catch 覆盖）。
 * 两级使用：level="app" 包整树兜底（白屏→错误卡+重载）；level="page" 包单页路由
 * （单页崩溃不拖垮 rail/导航，fallback 就地重试；路由切换由 key 复位）。
 * 零第三方依赖——40 行 class 可达成，不引 react-error-boundary（M17 OIDC 手写同哲学）。 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Card } from "./ui";

/** 动态 import 的 chunk 加载失败（重部署后旧 hash chunk 404）——与 SW precache 旧 bundle
 * 是同族问题，fallback 给「新版本已发布·立即刷新」而非笼统报错。 */
export function isChunkLoadError(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e);
  return /dynamically imported module|Importing a module script|Failed to fetch dynamically|ChunkLoadError|Loading chunk/i.test(
    msg,
  );
}

interface Props {
  level: "app" | "page";
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 现场诊断留痕（无上报服务面——一人工厂 console 即观测）。
    console.error(`[ErrorBoundary:${this.props.level}]`, error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (isChunkLoadError(error)) {
      return (
        <div className="flex h-full items-center justify-center bg-bg p-6">
          <Card className="max-w-md space-y-3 p-6 text-center">
            <div className="text-lg font-bold">🆙 新版本已发布</div>
            <p className="text-sm text-mut">页面资源已更新，刷新后即可使用最新版本。</p>
            <Button variant="primary" onClick={() => location.reload()}>🔄 立即刷新</Button>
          </Card>
        </div>
      );
    }
    const page = this.props.level === "page";
    return (
      <div className={page ? "p-6" : "flex h-full items-center justify-center bg-bg p-6"}>
        <Card className="max-w-md space-y-3 p-6">
          <div className="text-lg font-bold">⚠️ {page ? "这个页面出了问题" : "应用出了问题"}</div>
          <p className="text-sm text-mut">
            {page
              ? "页面渲染时发生错误，其余功能不受影响。"
              : "发生未预期的错误，重载可恢复。"}
          </p>
          <pre className="max-h-32 overflow-auto rounded-lg bg-bg p-2 text-xs text-mut">
            {String(error?.message ?? error)}
          </pre>
          {page ? (
            <Button variant="primary" onClick={() => this.setState({ error: null })}>↻ 重试</Button>
          ) : (
            <Button variant="primary" onClick={() => location.reload()}>🔄 重载</Button>
          )}
        </Card>
      </div>
    );
  }
}
