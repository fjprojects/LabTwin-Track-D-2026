// Labels describe the response we received, never an inferred AI success.
export function answerState(item) {
  if (item.mode === "insufficient_sources" || item.grounded === false) {
    return { kind: "unsupported", label: "More material needed" };
  }
  if (item.mode === "source_excerpts") {
    return { kind: "excerpts", label: "Source excerpts" };
  }
  if (item.mode === "ai_grounded" && item.grounded === true) {
    return { kind: "ai", label: "AI explanation · source-grounded" };
  }
  return { kind: "saved", label: "Saved answer" };
}

export function canCheckUnderstanding(role, item) {
  return role === "student" && item.grounded === true && item.id != null;
}
