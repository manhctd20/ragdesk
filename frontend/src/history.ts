import type { AskResult, HistoryTurn, Mode } from "./api";

export interface Turn { question: string; mode: Mode; provider?: string | null; askedAt: string; result: AskResult }
export interface Conversation { id: string; title: string; createdAt: string; updatedAt: string; turns: Turn[] }
export type DayGroup = "Hôm nay" | "Hôm qua" | "Tuần trước" | "Cũ hơn";

export const HISTORY_KEY = "tcnb:history";
export const THEME_KEY = "tcnb:theme";

export function applyStoredTheme(): void {
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch {
    // storage unavailable: follow the OS preference
  }
}

export function loadHistory(): Conversation[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
    return Array.isArray(data) ? (data as Conversation[]) : [];
  } catch {
    return [];
  }
}

export function saveHistory(list: Conversation[]): void {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
  } catch {
    // quota or blocked storage: history stays in memory only
  }
}

export function upsertConversation(list: Conversation[], c: Conversation): Conversation[] {
  return [c, ...list.filter((x) => x.id !== c.id)].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

const ORDER: DayGroup[] = ["Hôm nay", "Hôm qua", "Tuần trước", "Cũ hơn"];

function groupOf(iso: string, now: Date): DayGroup {
  const t = new Date(iso);
  const days = Math.round(
    (new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() -
      new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()) /
      86_400_000,
  );
  if (days <= 0) return "Hôm nay";
  if (days === 1) return "Hôm qua";
  return days <= 7 ? "Tuần trước" : "Cũ hơn";
}

export function groupByDay(list: Conversation[], now: Date = new Date()): { label: DayGroup; items: Conversation[] }[] {
  return ORDER.map((label) => ({ label, items: list.filter((c) => groupOf(c.updatedAt, now) === label) })).filter(
    (g) => g.items.length > 0,
  );
}

const HISTORY_TURNS = 3;

export function toHistory(turns: Turn[]): HistoryTurn[] {
  return turns.slice(-HISTORY_TURNS).map((t) => ({
    question: t.question,
    mode: t.mode,
    provider: t.provider ?? null,
    answer: t.result.answer,
  }));
}

export function newId(): string {
  const b = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}
