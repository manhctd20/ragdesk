import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import Chat from "./Chat";
import type { AskEvent, AskResult, Config, Source } from "./api";
import { HISTORY_KEY, upsertConversation, type Conversation } from "./history";

const QUESTION = "Nghỉ phép năm cần báo trước mấy ngày?";

const SOURCE: Source = {
  id: "doc1:3",
  text: "Người lao động phải gửi đơn ít nhất 03 ngày làm việc trước ngày nghỉ",
  meta: { doc_id: "doc1", filename: "NoiQuy_2026.docx", folder: "Nhân sự", file_type: "docx", section: "4.2 Nghỉ phép" },
  score: 0.032,
  matched: ["gửi", "đơn"],
};

const INTERNAL: AskResult = { answer: null, sources: [SOURCE], llm_error: null, message: null };

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const frame = ({ type, ...data }: AskEvent) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
const SSE_HEADERS = { "Content-Type": "text/event-stream" };

function sse(events: AskEvent[]): Response {
  return new Response(events.map(frame).join(""), { status: 200, headers: SSE_HEADERS });
}

function liveSse() {
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (c) => void (ctrl = c) });
  const enc = new TextEncoder();
  return {
    response: new Response(body, { status: 200, headers: SSE_HEADERS }),
    send: (...events: AskEvent[]) => events.forEach((e) => ctrl.enqueue(enc.encode(frame(e)))),
    close: () => ctrl.close(),
  };
}

const META: AskEvent = { type: "meta", sources: [SOURCE], query: null, message: null };
const DONE: AskEvent = { type: "done" };
const internalSse = () => sse([META, DONE]);
const externalSse = () =>
  sse([META, { type: "delta", text: "Cần trưởng phòng " }, { type: "delta", text: "duyệt [1]." }, DONE]);
const SENDS_OUT = "Câu hỏi, các đoạn liên quan và các lượt AI ngoài trước đó sẽ gửi tới AI ngoài";

type AskHandler = (body: unknown) => Response | Promise<Response>;

function stubFetch(config: Partial<Config>, onAsk: AskHandler) {
  const cfg: Config = { allow_external: false, providers: [], max_upload_mb: 20, ...config };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, "http://localhost").pathname;
    if (path === "/api/config") return json(200, cfg);
    if (path === "/api/ask/stream") return onAsk(JSON.parse(String(init?.body)));
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const askCalls = (m: ReturnType<typeof stubFetch>) =>
  m.mock.calls.filter(([input]) => String(input instanceof Request ? input.url : input).includes("/api/ask"));

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function Probe() {
  return <output data-testid="path">{useLocation().pathname}</output>;
}

function Page(props: { conversations: Conversation[]; onSave: (c: Conversation) => void }) {
  const { id } = useParams();
  return <Chat key={id ?? "new"} {...props} />;
}

function Harness({ initial, onSave }: { initial: Conversation[]; onSave: (c: Conversation) => void }) {
  const [list, setList] = useState(initial);
  const save = (c: Conversation) => {
    onSave(c);
    setList((l) => upsertConversation(l, c));
  };
  return (
    <>
      <Routes>
        <Route path="/" element={<Page conversations={list} onSave={save} />} />
        <Route path="/c/:id" element={<Page conversations={list} onSave={save} />} />
      </Routes>
      <Link to="/c/cu">Đi tới cuộc cũ</Link>
      <Probe />
    </>
  );
}

function show(path: string, conversations: Conversation[] = [], onSave = vi.fn()) {
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <Harness initial={conversations} onSave={onSave} />
    </MemoryRouter>,
  );
  return { ...view, onSave };
}

const box = () => screen.getByRole("textbox");
// A new conversation remounts Chat under /c/<id> after saving; wait for that before asserting on the answer.
const movedToSaved = () => waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent(/^\/c\//));
const toggle = () => {
  const t = screen.getAllByRole("button").find((b) => b.hasAttribute("aria-pressed"));
  if (!t) throw new Error("no toggle button with aria-pressed");
  return t;
};
const sendButton = () => {
  const b = screen.getAllByRole("button", { name: /gửi/i }).find((x) => !x.hasAttribute("aria-pressed"));
  if (!b) throw new Error("no send button");
  return b;
};

function existing(id: string, question = "Câu hỏi cũ về định mức"): Conversation {
  const at = new Date(2026, 10, 20, 9).toISOString();
  return {
    id,
    title: question,
    createdAt: at,
    updatedAt: at,
    turns: [{ question, mode: "internal", askedAt: at, result: INTERNAL }],
  };
}

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("Chat", () => {
  it("locks the external toggle when the server does not allow it, and explains in a toast on tap", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: false }, () => internalSse());
    show("/");
    expect(await screen.findByText(/Quản trị chưa cho phép gửi ra ngoài/)).toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-disabled", "true");
    await user.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(screen.getAllByRole("status").some((el) => el.textContent === "Quản trị chưa cho phép gửi ra ngoài")).toBe(true);
  });

  it("warns in a toast when the external toggle is switched on", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => externalSse());
    show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    expect(screen.getAllByRole("status").some((el) => el.textContent === SENDS_OUT)).toBe(true);
  });

  it("sends exactly {question, mode:'external', provider, history} and switches the toggle back off", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ allow_external: true, providers: ["gemini"] }, () => externalSse());
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "true");

    await user.type(box(), `${QUESTION}{Enter}`);
    await screen.findByText(/Cần trưởng phòng duyệt/);

    const calls = askCalls(fetchMock);
    expect(calls).toHaveLength(1);
    const [, init] = calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toStrictEqual({ question: QUESTION, mode: "external", provider: "gemini", history: [] });
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved: Conversation = onSave.mock.calls[0][0];
    expect(saved.turns[0]).toMatchObject({ question: QUESTION, mode: "external", provider: "gemini" });
    expect(saved.turns[0].result).toMatchObject({ answer: "Cần trưởng phòng duyệt [1].", query: null });

    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent(`/c/${saved.id}`));
    await user.type(box(), "Thế ai duyệt?{Enter}");
    await waitFor(() => expect(askCalls(fetchMock)).toHaveLength(2));
    expect(JSON.parse(String(askCalls(fetchMock)[1][1]?.body))).toStrictEqual({
      question: "Thế ai duyệt?",
      mode: "internal",
      history: [{ question: QUESTION, mode: "external", provider: "gemini", answer: "Cần trưởng phòng duyệt [1]." }],
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
    expect((onSave.mock.calls[1][0] as Conversation).turns.map((t) => t.question)).toEqual([QUESTION, "Thế ai duyệt?"]);
  });

  it("sends mode 'internal' by default", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ allow_external: true, providers: ["gemini"] }, () => internalSse());
    show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    await waitFor(() => expect(askCalls(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(askCalls(fetchMock)[0][1]?.body))).toStrictEqual({ question: QUESTION, mode: "internal", history: [] });
  });

  it("shows 'Đang tìm…' while an internal question is pending", async () => {
    const user = userEvent.setup();
    const pending = deferred<Response>();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => pending.promise);
    show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang tìm…/)).toBeInTheDocument();
    await act(async () => pending.resolve(internalSse()));
    await waitFor(() => expect(screen.queryByText(/Đang tìm…/)).toBeNull());
  });

  it("shows 'Đang viết câu trả lời…' while an external question is pending", async () => {
    const user = userEvent.setup();
    const pending = deferred<Response>();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => pending.promise);
    show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang viết câu trả lời…/)).toBeInTheDocument();
    await act(async () => pending.resolve(externalSse()));
  });

  it("on network failure shows 'Thử lại', does not save, and retry succeeds", async () => {
    const user = userEvent.setup();
    let n = 0;
    const fetchMock = stubFetch({}, () => {
      n += 1;
      if (n === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return internalSse();
    });
    const { onSave } = show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    const retry = await screen.findByRole("button", { name: /Thử lại/ });
    expect(onSave).not.toHaveBeenCalled();
    expect(localStorage.getItem(HISTORY_KEY) ?? "").not.toContain(QUESTION);

    await user.click(retry);
    await movedToSaved();
    expect(screen.getByText(/NoiQuy_2026\.docx/)).toBeInTheDocument();
    expect(askCalls(fetchMock)).toHaveLength(2);
    expect(JSON.parse(String(askCalls(fetchMock)[1][1]?.body))).toStrictEqual({ question: QUESTION, mode: "internal", history: [] });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Thử lại/ })).toBeNull();
  });

  it("calls onSave with a new conversation and moves the URL to /c/<id>", async () => {
    const user = userEvent.setup();
    stubFetch({}, () => internalSse());
    const { onSave } = show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved: Conversation = onSave.mock.calls[0][0];
    expect(saved.id).toBeTruthy();
    expect(saved.turns).toHaveLength(1);
    expect(saved.turns[0]).toMatchObject({ question: QUESTION, mode: "internal", result: INTERNAL });
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent(`/c/${saved.id}`));
  });

  it("App persists the asked question to localStorage", async () => {
    const user = userEvent.setup();
    stubFetch({}, () => internalSse());
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await user.type(screen.getByRole("textbox"), `${QUESTION}{Enter}`);
    await waitFor(() => expect(localStorage.getItem(HISTORY_KEY) ?? "").toContain(QUESTION));
    expect((await screen.findAllByRole("link", { name: new RegExp(QUESTION.slice(0, 20)) })).length).toBeGreaterThan(0);
  });

  it("disables send and does not call the API for a whitespace-only question", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({}, () => internalSse());
    show("/");
    expect(sendButton()).toBeDisabled();
    await user.type(box(), "   \t ");
    expect(sendButton()).toBeDisabled();
    await user.type(box(), "{Enter}");
    await user.click(sendButton());
    expect(askCalls(fetchMock)).toHaveLength(0);
  });

  it("does not send on Enter during IME composition; Shift+Enter inserts a newline", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({}, () => internalSse());
    show("/");
    await user.type(box(), "nghỉ phép");
    fireEvent.keyDown(box(), { key: "Enter", code: "Enter", keyCode: 229, isComposing: true });
    expect(askCalls(fetchMock)).toHaveLength(0);

    await user.type(box(), "{Shift>}{Enter}{/Shift}năm");
    expect(box()).toHaveValue("nghỉ phép\nnăm");
    expect(askCalls(fetchMock)).toHaveLength(0);
  });

  it("shows 'Không tìm thấy cuộc hỏi này' for an unknown /c/:id", async () => {
    stubFetch({}, () => internalSse());
    show("/c/khong-co", [existing("cu")]);
    expect(await screen.findByText(/Không tìm thấy cuộc hỏi này/)).toBeInTheDocument();
  });

  it("renders the turns of an existing conversation", async () => {
    stubFetch({}, () => internalSse());
    show("/c/cu", [existing("cu")]);
    expect(await screen.findByText("Câu hỏi cũ về định mức")).toBeInTheDocument();
    expect(screen.getAllByText(/NoiQuy_2026\.docx/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows the server detail on 403", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () =>
      json(403, { detail: "Chưa cho phép gửi ra ngoài" }),
    );
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Chưa cho phép gửi ra ngoài/)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("still saves but does not navigate when the user leaves while waiting", async () => {
    const user = userEvent.setup();
    const pending = deferred<Response>();
    stubFetch({}, () => pending.promise);
    const { onSave } = show("/", [existing("cu")]);
    await user.type(box(), `${QUESTION}{Enter}`);
    await screen.findByText(/Đang tìm…/);
    await user.click(screen.getByRole("link", { name: "Đi tới cuộc cũ" }));
    expect(screen.getByTestId("path")).toHaveTextContent("/c/cu");
    await act(async () => pending.resolve(internalSse()));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect((onSave.mock.calls[0][0] as Conversation).turns[0].question).toBe(QUESTION);
    expect(screen.getByTestId("path")).toHaveTextContent("/c/cu");
  });

  it("streams text progressively", async () => {
    const user = userEvent.setup();
    const live = liveSse();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => live.response);
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang viết câu trả lời…/)).toBeInTheDocument();

    await act(async () => live.send(META, { type: "delta", text: "Cần " }));
    expect(await screen.findByText("Cần")).toBeInTheDocument();
    expect(screen.queryByText(/Đang viết câu trả lời…/)).toBeNull();
    expect(onSave).not.toHaveBeenCalled();

    await act(async () => {
      live.send({ type: "delta", text: "trưởng phòng duyệt [1]." }, DONE);
      live.close();
    });
    await movedToSaved();
    expect(screen.getByText(/Cần trưởng phòng duyệt/)).toBeInTheDocument();
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("shows sources as soon as meta arrives", async () => {
    const user = userEvent.setup();
    const live = liveSse();
    stubFetch({}, () => live.response);
    const { onSave } = show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang tìm…/)).toBeInTheDocument();
    await act(async () => live.send(META));
    expect(await screen.findByText(/NoiQuy_2026\.docx/)).toBeInTheDocument();
    expect(screen.queryByText(/Đang tìm…/)).toBeNull();
    expect(onSave).not.toHaveBeenCalled();
    await act(async () => {
      live.send(DONE);
      live.close();
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
  });

  it("low relevance in external mode shows no answer and no \"Đang viết câu trả lời…\" after meta", async () => {
    const user = userEvent.setup();
    const live = liveSse();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => live.response);
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang viết câu trả lời…/)).toBeInTheDocument();
    await act(async () => live.send({ ...META, low_relevance: true } as AskEvent));
    expect(await screen.findByText("Không tìm thấy đoạn nào đủ liên quan")).toBeInTheDocument();
    expect(screen.queryByText(/Đang viết câu trả lời…/)).toBeNull();
    await act(async () => {
      live.send(DONE);
      live.close();
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0][0].turns[0].result.low_relevance).toBe(true);
  });

  it("error mid-stream keeps text and shows the error, then saves", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () =>
      sse([META, { type: "delta", text: "Cần trưởng " }, { type: "error", llm_error: "Không gọi được AI ngoài (RateLimitError)" }, DONE]),
    );
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    await movedToSaved();
    expect(screen.getByText(/Không gọi được AI ngoài \(RateLimitError\)/)).toBeInTheDocument();
    expect(screen.getByText("Cần trưởng")).toBeInTheDocument();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect((onSave.mock.calls[0][0] as Conversation).turns[0].result).toMatchObject({
      answer: "Cần trưởng ",
      llm_error: "Không gọi được AI ngoài (RateLimitError)",
    });
  });

  it("stream cut before done shows Thử lại and does not save", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => sse([META, { type: "delta", text: "Cần " }]));
    const { onSave } = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByRole("button", { name: /Thử lại/ })).toBeInTheDocument();
    expect(screen.getByText(/Không kết nối được máy chủ/)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("provider select appears only with 2+ providers", async () => {
    const user = userEvent.setup();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => externalSse());
    const one = show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    expect(screen.queryByRole("combobox")).toBeNull();
    one.unmount();

    const fetchMock = stubFetch({ allow_external: true, providers: ["claude", "openai", "gemini"] }, () => externalSse());
    show("/");
    const select = await screen.findByRole("combobox", { name: "Nhà cung cấp AI" });
    expect(Array.from((select as HTMLSelectElement).options, (o) => o.textContent)).toEqual(["Claude", "OpenAI", "Gemini"]);
    expect(select).toHaveValue("claude");
    expect(select).toBeDisabled();
    await user.click(toggle());
    expect(select).toBeEnabled();
    await user.selectOptions(select, "openai");
    expect(localStorage.getItem("tcnb:provider")).toBe("openai");
    await user.type(box(), `${QUESTION}{Enter}`);
    await waitFor(() => expect(askCalls(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(askCalls(fetchMock)[0][1]?.body))).toMatchObject({ mode: "external", provider: "openai" });
  });

  it("no provider list when external AI is not allowed, even with 3 providers", async () => {
    const fetchMock = stubFetch({ allow_external: false, providers: ["claude", "openai", "gemini"] }, () => internalSse());
    show("/");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("remembered provider that is no longer configured falls back to the first", async () => {
    const user = userEvent.setup();
    localStorage.setItem("tcnb:provider", "openai");
    const fetchMock = stubFetch({ allow_external: true, providers: ["gemini"] }, () => externalSse());
    show("/");
    await waitFor(() => expect(toggle()).toHaveAttribute("aria-disabled", "false"));
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    await waitFor(() => expect(askCalls(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(askCalls(fetchMock)[0][1]?.body))).toMatchObject({ mode: "external", provider: "gemini" });
  });

  it("old history without provider/query still renders", async () => {
    stubFetch({}, () => internalSse());
    const at = new Date(2026, 10, 20, 9).toISOString();
    const old = {
      id: "cu",
      title: "Câu hỏi cũ",
      createdAt: at,
      updatedAt: at,
      turns: [{ question: "Câu hỏi cũ", mode: "external", askedAt: at, result: { answer: "Trả lời cũ [1].", sources: [SOURCE], llm_error: null, message: null } }],
    };
    localStorage.setItem(HISTORY_KEY, JSON.stringify([old]));
    render(
      <MemoryRouter initialEntries={["/c/cu"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Trả lời cũ/)).toBeInTheDocument();
    expect(screen.getByText("AI ngoài: câu trả lời tổng hợp từ các đoạn")).toBeInTheDocument();
    expect(screen.queryByText(/Hiểu là/)).toBeNull();
  });
});
