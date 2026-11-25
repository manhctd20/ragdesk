export type Mode = "internal" | "external";
export interface Config { allow_external: boolean; providers: string[]; max_upload_mb: number }
export interface SourceMeta { doc_id: string; filename: string; folder: string; file_type: "pdf" | "docx" | "xlsx"; page?: number; section?: string; sheet?: string; row?: number }
export interface Source { id: string; text: string; meta: SourceMeta; score: number; matched: string[] }
export interface AskResult { answer: string | null; sources: Source[]; llm_error: string | null; message: string | null; query?: string | null; provider?: string | null }
export interface HistoryTurn { question: string; mode: Mode; provider: string | null; answer: string | null }
export interface AskRequest { question: string; mode: Mode; provider?: string; history: HistoryTurn[] }
export type AskEvent =
  | { type: "meta"; sources: Source[]; query: string | null; message: string | null }
  | { type: "delta"; text: string }
  | { type: "error"; llm_error: string }
  | { type: "done" };

export interface Doc { id: string; filename: string; folder: string; size_bytes: number; file_type: "pdf" | "docx" | "xlsx"; status: "indexing" | "ready" | "error"; progress_done: number; progress_total: number; error: string | null; chunk_count: number; replaces_id: string | null; created_at: string; updated_at: string }
export interface Folder { name: string; count: number }

export const ADMIN_KEY = "tcnb:admin";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Không kết nối được máy chủ");
  }
  if (!res.ok) throw await httpError(res);
  return res.json() as Promise<T>;
}

async function httpError(res: Response): Promise<ApiError> {
  const body: unknown = await res.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return new ApiError(res.status, typeof detail === "string" ? detail : `Máy chủ báo lỗi (${res.status})`);
}

export function getConfig(): Promise<Config> {
  return request<Config>("/api/config");
}

const NO_CONNECTION = "Không kết nối được máy chủ";

export async function askStream(req: AskRequest, onEvent: (e: AskEvent) => void): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch {
    throw new ApiError(0, NO_CONNECTION);
  }
  if (!res.ok) throw await httpError(res);
  if (!res.body) throw new ApiError(0, NO_CONNECTION);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;
  const dispatch = (block: string) => {
    let name = "";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trimStart();
    }
    if (!name) return;
    if (name === "done") done = true;
    onEvent({ type: name, ...(data ? JSON.parse(data) : {}) } as AskEvent);
  };
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      throw new ApiError(0, NO_CONNECTION);
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    let i: number;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      dispatch(buffer.slice(0, i));
      buffer = buffer.slice(i + 2);
    }
  }
  if (!done) throw new ApiError(0, NO_CONNECTION);
}

export function listDocuments(folder?: string): Promise<{ documents: Doc[]; folders: Folder[] }> {
  const qs = folder ? `?${new URLSearchParams({ folder })}` : "";
  return request(`/api/documents${qs}`);
}

async function adminRequest<T>(path: string, password: string, init: RequestInit = {}): Promise<T> {
  try {
    return await request<T>(path, { ...init, headers: { ...init.headers, "X-Admin-Password": password } });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) sessionStorage.removeItem(ADMIN_KEY);
    throw e;
  }
}

const stored = () => sessionStorage.getItem(ADMIN_KEY) ?? "";

export async function unlock(password: string): Promise<void> {
  await adminRequest("/api/admin/check", password, { method: "POST" });
  sessionStorage.setItem(ADMIN_KEY, password);
}

export function lock(): void {
  sessionStorage.removeItem(ADMIN_KEY);
}

export function isUnlocked(): boolean {
  return sessionStorage.getItem(ADMIN_KEY) !== null;
}

export function uploadDocument(file: File, folder: string): Promise<Doc> {
  const body = new FormData();
  body.append("file", file);
  body.append("folder", folder);
  return adminRequest("/api/documents", stored(), { method: "POST", body });
}

export async function deleteDocument(id: string): Promise<void> {
  await adminRequest(`/api/documents/${encodeURIComponent(id)}`, stored(), { method: "DELETE" });
}
