export type Mode = "internal" | "external";
export interface Config { allow_external: boolean; providers: string[]; max_upload_mb: number }
export interface SourceMeta { doc_id: string; filename: string; folder: string; file_type: "pdf" | "docx" | "xlsx"; page?: number; section?: string; sheet?: string; row?: number }
export interface Source { id: string; text: string; meta: SourceMeta; score: number; matched: string[] }
export interface AskResult { answer: string | null; sources: Source[]; llm_error: string | null; message: string | null }

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
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Máy chủ báo lỗi (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function getConfig(): Promise<Config> {
  return request<Config>("/api/config");
}

export function ask(question: string, mode: Mode): Promise<AskResult> {
  return request<AskResult>("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode }),
  });
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
