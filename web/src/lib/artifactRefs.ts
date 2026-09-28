/** I214: artifact reference extraction — write-back comments (I209) and any
 * markdown body may cite an artifact path inside backticks; these refs become
 * clickable preview badges next to the comment body. */

/** 匹配反引号中的工件路径引用：`artifacts/…`（含中文/点/连字符/斜杠）。 */
const REF_RE = /`((?:artifacts)\/[^\s`]+)`/g;

export function extractArtifactRefs(body: string): string[] {
  const out: string[] = [];
  for (const m of body.matchAll(REF_RE)) {
    if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

/** 工件路径的短显示名（尾段），供徽标文案。 */
export function artifactShortName(path: string): string {
  return path.split("/").pop() ?? path;
}
