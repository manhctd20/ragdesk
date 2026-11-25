import { describe, expect, it } from "vitest";
import { formatWhen, highlight, splitCitations, whereLabel } from "./format";
import type { SourceMeta } from "./api";

const hits = (segs: { text: string; hit: boolean }[]) => segs.filter((s) => s.hit).map((s) => s.text);
const joined = (segs: { text: string; hit: boolean }[]) => segs.map((s) => s.text).join("");

describe("highlight", () => {
  it("matches case-insensitively with Vietnamese diacritics", () => {
    const segs = highlight("Người lao động GỬI đơn", ["gửi", "đơn"]);
    expect(hits(segs)).toEqual(["GỬI", "đơn"]);
    expect(joined(segs)).toBe("Người lao động GỬI đơn");
  });

  it("does not match a base letter inside an accented letter", () => {
    expect(hits(highlight("ăn", ["a"]))).toEqual([]);
  });

  it("matches whole words only", () => {
    expect(hits(highlight("mang theo đơngiản và đơn", ["an", "đơn"]))).toEqual(["đơn"]);
  });

  it.each([["c++"], ["("], ["[a-"], ["*"], ["\\"]])("does not throw on regex metachar term %s", (t) => {
    const text = "Ngôn ngữ c++ (cũ) [a-z] * \\ hết";
    expect(() => highlight(text, [t])).not.toThrow();
    expect(joined(highlight(text, [t]))).toBe(text);
  });

  it("matches NFD text against NFC terms", () => {
    const text = "Người gửi đơn".normalize("NFD");
    const found = hits(highlight(text, ["gửi"]));
    expect(found).toHaveLength(1);
    expect(found[0].normalize("NFC")).toBe("gửi");
  });

  it("returns the whole text unmarked when terms are empty", () => {
    const segs = highlight("Nội quy 2026", []);
    expect(hits(segs)).toEqual([]);
    expect(joined(segs)).toBe("Nội quy 2026");
  });

  it("ignores empty-string terms", () => {
    const segs = highlight("Nội quy", [""]);
    expect(hits(segs)).toEqual([]);
    expect(joined(segs)).toBe("Nội quy");
  });
});

describe("splitCitations", () => {
  const show = (parts: (string | number)[]) =>
    parts.map((p) => (typeof p === "number" ? `#${p}` : p)).join("");

  it("turns in-range citations into numbers and keeps out-of-range as text", () => {
    const parts = splitCitations("A [1] B [2][3] C [1, 2] D [9]", 3);
    expect(parts.filter((p) => typeof p === "number")).toEqual([1, 2, 3, 1, 2]);
    expect(show(parts)).toMatch(/^A\s*#1\s*B\s*#2\s*#3\s*C\s*#1\W*#2\s*D \[9\]$/);
  });

  it("keeps [0] and all citations as text when count is 0", () => {
    const parts = splitCitations("Không có [0] và [1]", 0);
    expect(parts.filter((p) => typeof p === "number")).toEqual([]);
    expect(parts.join("")).toBe("Không có [0] và [1]");
  });

  it("returns plain text unchanged", () => {
    expect(splitCitations("Không tìm thấy trong tài liệu", 5).join("")).toBe("Không tìm thấy trong tài liệu");
  });
});

describe("whereLabel", () => {
  const base: SourceMeta = { doc_id: "d1", filename: "NoiQuy_2026.docx", folder: "Nhân sự", file_type: "docx" };

  it("formats page", () => {
    expect(whereLabel({ ...base, file_type: "pdf", page: 7 })).toBe("Trang 7");
  });

  it("formats section", () => {
    expect(whereLabel({ ...base, section: "4.2 Nghỉ phép" })).toBe("Mục 4.2 Nghỉ phép");
  });

  it("formats sheet and row", () => {
    expect(whereLabel({ ...base, file_type: "xlsx", sheet: "Quy định", row: 12 })).toBe("Sheet Quy định, dòng 12");
  });

  it("returns empty string without location keys", () => {
    expect(whereLabel(base)).toBe("");
  });
});

describe("formatWhen", () => {
  const now = new Date(2026, 10, 21, 10, 0, 0);

  it("says 'Vừa xong' under 60 seconds", () => {
    expect(formatWhen(new Date(2026, 10, 21, 9, 59, 1).toISOString(), now)).toBe("Vừa xong");
  });

  it("uses dd/mm/yyyy from 60 seconds on", () => {
    expect(formatWhen(new Date(2026, 10, 21, 9, 59, 0).toISOString(), now)).toBe("21/11/2026");
    expect(formatWhen(new Date(2026, 10, 18, 8, 0).toISOString(), now)).toBe("18/11/2026");
  });

  it("zero-pads day and month", () => {
    expect(formatWhen(new Date(2026, 0, 5, 23, 30).toISOString(), now)).toBe("05/01/2026");
  });
});
