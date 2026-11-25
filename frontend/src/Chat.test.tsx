import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import Chat from "./Chat";
import type { AskResult, Config, Source } from "./api";
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
const EXTERNAL: AskResult = { answer: "Cần trưởng phòng duyệt [1].", sources: [SOURCE], llm_error: null, message: null };

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type AskHandler = (body: unknown) => Response | Promise<Response>;

function stubFetch(config: Partial<Config>, onAsk: AskHandler) {
  const cfg: Config = { allow_external: false, providers: [], max_upload_mb: 20, ...config };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, "http://localhost").pathname;
    if (path === "/api/config") return json(200, cfg);
    if (path === "/api/ask") return onAsk(JSON.parse(String(init?.body)));
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
  it("locks the external toggle when the server does not allow it", async () => {
    stubFetch({ allow_external: false }, () => json(200, INTERNAL));
    show("/");
    expect(await screen.findByText(/Quản trị chưa cho phép gửi ra ngoài/)).toBeInTheDocument();
    expect(toggle()).toBeDisabled();
  });

  it("sends exactly {question, mode:'external'} and switches the toggle back off", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ allow_external: true, providers: ["gemini"] }, () => json(200, EXTERNAL));
    const { onSave } = show("/c/cu", [existing("cu")]);
    await waitFor(() => expect(toggle()).toBeEnabled());
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle());
    expect(toggle()).toHaveAttribute("aria-pressed", "true");

    await user.type(box(), `${QUESTION}{Enter}`);
    await screen.findByText(/Cần trưởng phòng duyệt/);

    const calls = askCalls(fetchMock);
    expect(calls).toHaveLength(1);
    const [, init] = calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toStrictEqual({ question: QUESTION, mode: "external" });
    expect(String(init?.body)).not.toContain("Câu hỏi cũ về định mức");
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(onSave).toHaveBeenCalled();
    const saved: Conversation = onSave.mock.calls.at(-1)![0];
    expect(saved.id).toBe("cu");
    expect(saved.turns.map((t) => t.question)).toEqual(["Câu hỏi cũ về định mức", QUESTION]);
    expect(saved.turns[1].mode).toBe("external");
  });

  it("sends mode 'internal' by default", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ allow_external: true, providers: ["gemini"] }, () => json(200, INTERNAL));
    show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    await waitFor(() => expect(askCalls(fetchMock)).toHaveLength(1));
    expect(JSON.parse(String(askCalls(fetchMock)[0][1]?.body))).toStrictEqual({ question: QUESTION, mode: "internal" });
  });

  it("shows 'Đang tìm…' while an internal question is pending", async () => {
    const user = userEvent.setup();
    const pending = deferred<Response>();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => pending.promise);
    show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang tìm…/)).toBeInTheDocument();
    await act(async () => pending.resolve(json(200, INTERNAL)));
    await waitFor(() => expect(screen.queryByText(/Đang tìm…/)).toBeNull());
  });

  it("shows 'Đang viết câu trả lời…' while an external question is pending", async () => {
    const user = userEvent.setup();
    const pending = deferred<Response>();
    stubFetch({ allow_external: true, providers: ["gemini"] }, () => pending.promise);
    show("/");
    await waitFor(() => expect(toggle()).toBeEnabled());
    await user.click(toggle());
    await user.type(box(), `${QUESTION}{Enter}`);
    expect(await screen.findByText(/Đang viết câu trả lời…/)).toBeInTheDocument();
    await act(async () => pending.resolve(json(200, EXTERNAL)));
  });

  it("on network failure shows 'Thử lại', does not save, and retry succeeds", async () => {
    const user = userEvent.setup();
    let n = 0;
    const fetchMock = stubFetch({}, () => {
      n += 1;
      if (n === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return json(200, INTERNAL);
    });
    const { onSave } = show("/");
    await user.type(box(), `${QUESTION}{Enter}`);
    const retry = await screen.findByRole("button", { name: /Thử lại/ });
    expect(onSave).not.toHaveBeenCalled();
    expect(localStorage.getItem(HISTORY_KEY) ?? "").not.toContain(QUESTION);

    await user.click(retry);
    expect(await screen.findByText(/NoiQuy_2026\.docx/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(askCalls(fetchMock)).toHaveLength(2);
    expect(JSON.parse(String(askCalls(fetchMock)[1][1]?.body))).toStrictEqual({ question: QUESTION, mode: "internal" });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Thử lại/ })).toBeNull();
  });

  it("calls onSave with a new conversation and moves the URL to /c/<id>", async () => {
    const user = userEvent.setup();
    stubFetch({}, () => json(200, INTERNAL));
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
    stubFetch({}, () => json(200, INTERNAL));
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
    const fetchMock = stubFetch({}, () => json(200, INTERNAL));
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
    const fetchMock = stubFetch({}, () => json(200, INTERNAL));
    show("/");
    await user.type(box(), "nghỉ phép");
    fireEvent.keyDown(box(), { key: "Enter", code: "Enter", keyCode: 229, isComposing: true });
    expect(askCalls(fetchMock)).toHaveLength(0);

    await user.type(box(), "{Shift>}{Enter}{/Shift}năm");
    expect(box()).toHaveValue("nghỉ phép\nnăm");
    expect(askCalls(fetchMock)).toHaveLength(0);
  });

  it("shows 'Không tìm thấy cuộc hỏi này' for an unknown /c/:id", async () => {
    stubFetch({}, () => json(200, INTERNAL));
    show("/c/khong-co", [existing("cu")]);
    expect(await screen.findByText(/Không tìm thấy cuộc hỏi này/)).toBeInTheDocument();
  });

  it("renders the turns of an existing conversation", async () => {
    stubFetch({}, () => json(200, INTERNAL));
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
    await waitFor(() => expect(toggle()).toBeEnabled());
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
    await act(async () => pending.resolve(json(200, INTERNAL)));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect((onSave.mock.calls[0][0] as Conversation).turns[0].question).toBe(QUESTION);
    expect(screen.getByTestId("path")).toHaveTextContent("/c/cu");
  });
});
