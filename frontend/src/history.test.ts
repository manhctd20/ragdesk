import { afterEach, describe, expect, it, vi } from "vitest";
import type { AskResult } from "./api";
import {
  HISTORY_KEY,
  groupByDay,
  loadHistory,
  newId,
  saveHistory,
  toHistory,
  HISTORY_QUESTION_MAX,
  HISTORY_ANSWER_MAX,
  upsertConversation,
  type Conversation,
  type Turn,
} from "./history";

const RESULT: AskResult = { answer: null, sources: [], llm_error: null, message: "Chưa có tài liệu nào" };

function conv(id: string, updatedAt: string, title = `Cuộc hỏi ${id}`): Conversation {
  return {
    id,
    title,
    createdAt: updatedAt,
    updatedAt,
    turns: [{ question: "Nghỉ phép năm được bao nhiêu ngày?", mode: "internal", askedAt: updatedAt, result: RESULT }],
  };
}

const local = (y: number, m: number, d: number, h = 12, min = 0) => new Date(y, m - 1, d, h, min).toISOString();

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("loadHistory", () => {
  it("returns [] when nothing stored", () => {
    expect(loadHistory()).toEqual([]);
  });

  it.each([["{rác"], ["{}"], ["null"], ['"chuỗi"']])("returns [] for corrupt value %s", (raw) => {
    localStorage.setItem(HISTORY_KEY, raw);
    expect(loadHistory()).toEqual([]);
  });

  it("returns [] when getItem throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(loadHistory()).toEqual([]);
  });
});

describe("saveHistory", () => {
  it("round-trips with Vietnamese text intact", () => {
    const list = [conv("a", local(2026, 11, 21)), conv("b", local(2026, 11, 20), "Định mức công tác phí ữ ặ ỡ")];
    saveHistory(list);
    expect(localStorage.getItem(HISTORY_KEY)).not.toBeNull();
    expect(loadHistory()).toEqual(list);
  });

  it("swallows QuotaExceededError", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(() => saveHistory([conv("a", local(2026, 11, 21))])).not.toThrow();
  });
});

describe("upsertConversation", () => {
  it("replaces same id and sorts by updatedAt desc", () => {
    const a = conv("a", local(2026, 11, 19));
    const b = conv("b", local(2026, 11, 20));
    const c = conv("c", local(2026, 11, 18));
    const a2 = { ...conv("a", local(2026, 11, 21)), title: "Đã cập nhật" };
    const out = upsertConversation([b, a, c], a2);
    expect(out.map((x) => x.id)).toEqual(["a", "b", "c"]);
    expect(out[0].title).toBe("Đã cập nhật");
    expect(out.filter((x) => x.id === "a")).toHaveLength(1);
  });

  it("adds a new conversation", () => {
    const a = conv("a", local(2026, 11, 19));
    const n = conv("n", local(2026, 11, 18));
    expect(upsertConversation([a], n).map((x) => x.id)).toEqual(["a", "n"]);
  });

  it("does not mutate the input list", () => {
    const list = [conv("a", local(2026, 11, 19))];
    upsertConversation(list, conv("b", local(2026, 11, 20)));
    expect(list.map((x) => x.id)).toEqual(["a"]);
  });
});

describe("groupByDay", () => {
  const now = new Date("2026-11-21T10:00");
  const labelOf = (groups: ReturnType<typeof groupByDay>, id: string) =>
    groups.find((g) => g.items.some((c) => c.id === id))?.label;

  it.each([
    ["today-0001", local(2026, 11, 21, 0, 1), "Hôm nay"],
    ["today-noon", local(2026, 11, 21, 9, 59), "Hôm nay"],
    ["yesterday-2359", local(2026, 11, 20, 23, 59), "Hôm qua"],
    ["d19", local(2026, 11, 19, 12), "Tuần trước"],
    ["d14-7days", local(2026, 11, 14, 0, 1), "Tuần trước"],
    ["d13-8days", local(2026, 11, 13, 23, 59), "Cũ hơn"],
    ["d01", local(2026, 11, 1), "Cũ hơn"],
    ["future", local(2026, 11, 23), "Hôm nay"],
  ])("%s → %s", (id, when, label) => {
    expect(labelOf(groupByDay([conv(id, when)], now), id)).toBe(label);
  });

  it("crosses a month boundary by calendar day", () => {
    const dec1 = new Date(2026, 11, 1, 8, 0);
    const groups = groupByDay([conv("nov30", local(2026, 11, 30, 23, 0))], dec1);
    expect(labelOf(groups, "nov30")).toBe("Hôm qua");
  });

  it("keeps fixed group order and omits empty groups", () => {
    const list = [
      conv("old", local(2026, 11, 1)),
      conv("today", local(2026, 11, 21, 8)),
      conv("week", local(2026, 11, 17)),
    ];
    const groups = groupByDay(list, now);
    expect(groups.map((g) => g.label)).toEqual(["Hôm nay", "Tuần trước", "Cũ hơn"]);
    expect(groups.every((g) => g.items.length > 0)).toBe(true);
  });

  it("returns [] for an empty list", () => {
    expect(groupByDay([], now)).toEqual([]);
  });
});

describe("newId", () => {
  it("works without crypto.randomUUID and is unique", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto), randomUUID: undefined });
    const a = newId();
    const b = newId();
    expect(typeof a).toBe("string");
    expect(a.length).toBeGreaterThan(0);
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});

describe("toHistory", () => {
  it("keeps the last 3 turns, maps provider (missing → null) and never includes sources", () => {
    const src = { id: "d:1", text: "t", meta: { doc_id: "d", filename: "f.pdf", folder: "x", file_type: "pdf" as const }, score: 1, matched: [] };
    const turn = (n: number, extra: Partial<Turn> = {}): Turn => ({
      question: `Câu ${n}`,
      mode: "external",
      askedAt: "2026-11-21T10:00:00Z",
      result: { answer: `Đáp ${n}`, sources: [src], llm_error: null, message: null, query: `q${n}` },
      ...extra,
    });
    const out = toHistory([turn(1), turn(2, { provider: "claude" }), turn(3, { mode: "internal", result: { answer: null, sources: [src], llm_error: null, message: null } }), turn(4, { provider: "gemini" })]);
    expect(out).toEqual([
      { question: "Câu 2", mode: "external", provider: "claude", answer: "Đáp 2" },
      { question: "Câu 3", mode: "internal", provider: null, answer: null },
      { question: "Câu 4", mode: "external", provider: "gemini", answer: "Đáp 4" },
    ]);
    expect(JSON.stringify(out)).not.toContain("sources");
    expect(toHistory([])).toEqual([]);
  });

  it("clips question and answer to the server limits, counting code points", () => {
    const result = { answer: "đ".repeat(HISTORY_ANSWER_MAX) + "😀thừa", sources: [], llm_error: null, message: null };
    const [out] = toHistory([{ question: "ê".repeat(HISTORY_QUESTION_MAX - 1) + "😀thừa", mode: "external", askedAt: "2026-11-21T10:00:00Z", result }]);
    expect(Array.from(out.question)).toHaveLength(HISTORY_QUESTION_MAX);
    expect(out.question.endsWith("😀")).toBe(true);
    expect(out.answer).toBe("đ".repeat(HISTORY_ANSWER_MAX));
    expect(HISTORY_QUESTION_MAX).toBe(2000);
    expect(HISTORY_ANSWER_MAX).toBe(8000);
  });
});
