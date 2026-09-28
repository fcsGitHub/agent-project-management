import { describe, expect, it } from "vitest";
import { artifactShortName, extractArtifactRefs } from "./artifactRefs";

describe("extractArtifactRefs", () => {
  it("extracts backtick artifact paths, deduplicated, in order", () => {
    const body = [
      "🤖 Agent 产出已回流（run `r_wb1`）", // run id 反引号不算工件引用
      "- 工件路径：`artifacts/prd/feature-auth.md`",
      "- 见 `artifacts/prd/feature-auth.md` 与 `artifacts/wbs/plan.md`",
    ].join("\n");
    expect(extractArtifactRefs(body)).toEqual([
      "artifacts/prd/feature-auth.md",
      "artifacts/wbs/plan.md",
    ]);
  });

  it("ignores non-artifact backtick spans and bare paths", () => {
    const body = "看 `docs/x.md` 和 artifacts/prd/bare.md，只有 `artifacts/ok.md` 算";
    expect(extractArtifactRefs(body)).toEqual(["artifacts/ok.md"]);
  });
});

describe("artifactShortName", () => {
  it("returns the trailing segment", () => {
    expect(artifactShortName("artifacts/prd/feature-auth.md")).toBe("feature-auth.md");
    expect(artifactShortName("artifacts/plan.md")).toBe("plan.md");
  });
});
