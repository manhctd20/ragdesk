import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, askStream, type AskEvent, type AskRequest } from "./api";

const enc = new TextEncoder();

function streamOf(chunks: Uint8Array[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(x));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const sse = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

const REQ: AskRequest = { question: "Nghỉ phép?", mode: "external", provider: "claude", history: [] };

async function collect(req: AskRequest = REQ): Promise<AskEvent[]> {
  const events: AskEvent[] = [];
  await askStream(req, (e) => events.push(e));
  return events;
}

afterEach(() => vi.unstubAllGlobals());

describe("askStream", () => {
  it("parses events in order", async () => {
    const text = sse("meta", { sources: [], query: "Hiểu là X", message: null }) + sse("delta", { text: "Xin " }) + sse("delta", { text: "chào" }) + sse("error", { llm_error: "hết hạn mức" }) + sse("done", {});
    vi.stubGlobal("fetch", vi.fn(async () => streamOf([enc.encode(text)])));
    expect(await collect()).toEqual([
      { type: "meta", sources: [], query: "Hiểu là X", message: null },
      { type: "delta", text: "Xin " },
      { type: "delta", text: "chào" },
      { type: "error", llm_error: "hết hạn mức" },
      { type: "done" },
    ]);
  });

  it("handles an event split across chunks, including inside a multi-byte Vietnamese character", async () => {
    const bytes = enc.encode(sse("delta", { text: "Nghỉ phép năm được hưởng" }) + sse("done", {}));
    const cut = bytes.indexOf(0xe1) + 1; // "ỉ" is 3 bytes (E1 BB 89): split after its first byte
    const chunks = [bytes.slice(0, cut), bytes.slice(cut, cut + 1), bytes.slice(cut + 1, bytes.length - 3), bytes.slice(bytes.length - 3)];
    vi.stubGlobal("fetch", vi.fn(async () => streamOf(chunks)));
    expect(await collect()).toEqual([{ type: "delta", text: "Nghỉ phép năm được hưởng" }, { type: "done" }]);
  });

  it("throws ApiError(403) with detail before streaming", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Chế độ AI ngoài đang tắt" }), { status: 403 })));
    await expect(collect()).rejects.toMatchObject({ name: "Error", status: 403, message: "Chế độ AI ngoài đang tắt" });
    await expect(collect()).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError(0) when the stream ends without done", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => streamOf([enc.encode(sse("delta", { text: "dở" }))])));
    await expect(collect()).rejects.toMatchObject({ status: 0, message: "Không kết nối được máy chủ" });
  });

  it("throws ApiError(0) when fetch itself fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(collect()).rejects.toMatchObject({ status: 0, message: "Không kết nối được máy chủ" });
  });

  it("posts exactly {question, mode, provider, history}", async () => {
    const fetchMock = vi.fn(async (_u: RequestInfo | URL, _i?: RequestInit) => streamOf([enc.encode(sse("done", {}))]));
    vi.stubGlobal("fetch", fetchMock);
    const history = [{ question: "Q1", mode: "external" as const, provider: "claude", answer: "A1" }];
    await collect({ ...REQ, history });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/ask/stream");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ question: "Nghỉ phép?", mode: "external", provider: "claude", history });
  });
});
