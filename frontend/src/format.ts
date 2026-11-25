import type { SourceMeta } from "./api";

const WORD = String.raw`[\p{L}\p{N}\p{M}_]`;

export function highlight(text: string, terms: string[]): { text: string; hit: boolean }[] {
  const nfc = text.normalize("NFC");
  const alt = terms
    .map((t) => t.normalize("NFC"))
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  if (!alt) return [{ text: nfc, hit: false }];
  const re = new RegExp(`(?<!${WORD})(?:${alt})(?!${WORD})`, "giu");
  const out: { text: string; hit: boolean }[] = [];
  let last = 0;
  for (const m of nfc.matchAll(re)) {
    if (m.index > last) out.push({ text: nfc.slice(last, m.index), hit: false });
    out.push({ text: m[0], hit: true });
    last = m.index + m[0].length;
  }
  if (last < nfc.length) out.push({ text: nfc.slice(last), hit: false });
  return out;
}

export function splitCitations(answer: string, count: number): (string | number)[] {
  const out: (string | number)[] = [];
  const pushText = (s: string) => {
    if (!s) return;
    if (typeof out.at(-1) === "string") out[out.length - 1] += s;
    else out.push(s);
  };
  let last = 0;
  for (const m of answer.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)) {
    const nums = m[1].split(",").map(Number);
    pushText(answer.slice(last, m.index));
    last = m.index + m[0].length;
    if (nums.every((n) => n >= 1 && n <= count)) {
      nums.forEach((n, i) => {
        if (i > 0) pushText(", ");
        out.push(n);
      });
    } else pushText(m[0]);
  }
  pushText(answer.slice(last));
  return out;
}

export function whereLabel(meta: SourceMeta): string {
  if (meta.page != null) return `Trang ${meta.page}`;
  if (meta.section) return `Mục ${meta.section}`;
  if (meta.sheet) return `Sheet ${meta.sheet}${meta.row != null ? `, dòng ${meta.row}` : ""}`;
  return "";
}

export function formatWhen(iso: string, now: Date = new Date()): string {
  const t = new Date(iso);
  if (now.getTime() - t.getTime() < 60_000) return "Vừa xong";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(t.getDate())}/${p(t.getMonth() + 1)}/${t.getFullYear()}`;
}
