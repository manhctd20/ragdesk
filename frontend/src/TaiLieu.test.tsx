import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import TaiLieu from "./TaiLieu";
import { ADMIN_KEY, type Doc, type Folder } from "./api";

const PW = "Mat-khau-dung-2026";

function doc(id: string, filename: string, folder: string, over: Partial<Doc> = {}): Doc {
  return {
    id,
    filename,
    folder,
    size_bytes: 1024,
    file_type: filename.endsWith(".xlsx") ? "xlsx" : filename.endsWith(".docx") ? "docx" : "pdf",
    status: "ready",
    progress_done: 0,
    progress_total: 0,
    error: null,
    chunk_count: 12,
    replaces_id: null,
    created_at: "2026-11-18T03:00:00+00:00",
    updated_at: "2026-11-18T03:00:00+00:00",
    ...over,
  };
}

const READY = doc("d-ready", "NoiQuy_2026.docx", "Nhân sự");
const INDEXING = doc("d-idx", "QuyTrinhDuyet.pdf", "Nhân sự", {
  status: "indexing",
  progress_done: 3,
  progress_total: 10,
  chunk_count: 0,
});
const FAILED = doc("d-err", "HoaDon_Scan.pdf", "Kế toán", {
  status: "error",
  error: "PDF chỉ có ảnh scan, không đọc được chữ",
  chunk_count: 0,
});
const FOLDERS: Folder[] = [
  { name: "Nhân sự", count: 2 },
  { name: "Kế toán", count: 1 },
];

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type Req = { url: URL; method: string; init: RequestInit | undefined; headers: Headers };
type H = (req: Req) => Response | Promise<Response>;

function stubFetch(h: { config?: H; list?: H; check?: H; upload?: H; remove?: H } = {}) {
  const handlers = {
    config: h.config ?? (() => json(200, { allow_external: false, providers: [], max_upload_mb: 20 })),
    list: h.list ?? (() => json(200, { documents: [READY, FAILED], folders: FOLDERS })),
    check: h.check ?? (() => json(200, { ok: true })),
    upload: h.upload ?? (() => json(202, doc("d-new", "moi.pdf", "Nhân sự", { status: "indexing" }))),
    remove: h.remove ?? ((r: Req) => json(202, { id: r.url.pathname.split("/").pop() })),
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const req: Req = { url, method, init, headers: new Headers(init?.headers) };
    if (url.pathname === "/api/config") return handlers.config(req);
    if (url.pathname === "/api/admin/check" && method === "POST") return handlers.check(req);
    if (url.pathname === "/api/documents" && method === "GET") return handlers.list(req);
    if (url.pathname === "/api/documents" && method === "POST") return handlers.upload(req);
    if (url.pathname.startsWith("/api/documents/") && method === "DELETE") return handlers.remove(req);
    throw new Error(`unexpected fetch ${method} ${raw}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const calls = (pred: (r: { url: URL; method: string; init?: RequestInit }) => boolean) =>
    fetchMock.mock.calls
      .map(([input, init]) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        return { url: new URL(raw, "http://localhost"), method: (init?.method ?? "GET").toUpperCase(), init };
      })
      .filter(pred);
  return {
    fetchMock,
    lists: () => calls((c) => c.url.pathname === "/api/documents" && c.method === "GET"),
    uploads: () => calls((c) => c.url.pathname === "/api/documents" && c.method === "POST"),
    deletes: () => calls((c) => c.url.pathname.startsWith("/api/documents/") && c.method === "DELETE"),
    checks: () => calls((c) => c.url.pathname === "/api/admin/check"),
    configs: () => calls((c) => c.url.pathname === "/api/config"),
  };
}

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
  return <output data-testid="search">{useLocation().search}</output>;
}

function show(path = "/tai-lieu") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tai-lieu" element={<TaiLieu />} />
      </Routes>
      <Probe />
    </MemoryRouter>,
  );
}

const rowOf = (filename: string) => {
  const tr = screen.getByText(filename).closest("tr");
  if (!tr) throw new Error(`no row for ${filename}`);
  return tr;
};
const fileInput = (container: HTMLElement) => container.querySelector<HTMLInputElement>('input[type="file"]');
const tab = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name}`) });

function bigFile(name: string, bytes: number) {
  const f = new File(["x"], name, { type: "application/pdf" });
  Object.defineProperty(f, "size", { value: bytes });
  return f;
}
const pdf = (name: string) => new File(["%PDF-1.4"], name, { type: "application/pdf" });

async function unlockWith(user: ReturnType<typeof userEvent.setup>, password: string) {
  await user.click(screen.getAllByRole("button", { name: /Mở khoá quản trị/ })[0]);
  await user.type(screen.getByLabelText("Mật khẩu quản trị"), `${password}{Enter}`);
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("TaiLieu: states", () => {
  it("shows aria-busy and a skeleton while loading", async () => {
    const pending = deferred<Response>();
    stubFetch({ list: () => pending.promise });
    const { container } = show();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelectorAll(".sk").length).toBeGreaterThan(0);
    await act(async () => pending.resolve(json(200, { documents: [READY], folders: FOLDERS })));
    expect(await screen.findByText("NoiQuy_2026.docx")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
  });

  it("shows the empty state", async () => {
    stubFetch({ list: () => json(200, { documents: [], folders: [] }) });
    show();
    expect(await screen.findByText("Chưa có tài liệu nào")).toBeInTheDocument();
  });

  it("shows the error state and retries", async () => {
    const user = userEvent.setup();
    let n = 0;
    const api = stubFetch({
      list: () => {
        n += 1;
        return n === 1 ? Promise.reject(new TypeError("Failed to fetch")) : json(200, { documents: [READY], folders: FOLDERS });
      },
    });
    show();
    expect(await screen.findByText(/Không kết nối được máy chủ/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Thử lại/ }));
    expect(await screen.findByText("NoiQuy_2026.docx")).toBeInTheDocument();
    expect(api.lists()).toHaveLength(2);
    expect(screen.queryByText(/Không kết nối được máy chủ/)).toBeNull();
  });

  it("shows each row with name, folder and status; indexing shows 'đoạn 3/10' without delete", async () => {
    sessionStorage.setItem(ADMIN_KEY, PW);
    stubFetch({ list: () => json(200, { documents: [INDEXING, READY, FAILED], folders: FOLDERS }) });
    show();
    await screen.findByText("NoiQuy_2026.docx");

    const ready = rowOf("NoiQuy_2026.docx");
    expect(within(ready).getByText("Nhân sự")).toBeInTheDocument();
    expect(within(ready).getByText(/Sẵn sàng/)).toBeInTheDocument();
    expect(within(ready).getByRole("button", { name: "Xoá NoiQuy_2026.docx" })).toBeInTheDocument();

    const idx = rowOf("QuyTrinhDuyet.pdf");
    expect(within(idx).getByText(/đoạn 3\/10/)).toBeInTheDocument();
    expect(within(idx).queryByRole("button", { name: /Xoá/ })).toBeNull();

    const failed = rowOf("HoaDon_Scan.pdf");
    expect(within(failed).getByText("Kế toán")).toBeInTheDocument();
    expect(within(failed).getByText(/PDF chỉ có ảnh scan, không đọc được chữ/)).toBeInTheDocument();
  });

  it("does not show '0/0' when progress_total is 0", async () => {
    stubFetch({
      list: () =>
        json(200, {
          documents: [doc("d0", "Moi.pdf", "Nhân sự", { status: "indexing", progress_done: 0, progress_total: 0 })],
          folders: FOLDERS,
        }),
    });
    show();
    await screen.findByText("Moi.pdf");
    const row = rowOf("Moi.pdf");
    expect(row.textContent).toMatch(/Đang index/);
    expect(row.textContent).not.toContain("0/0");
  });

  it("renders untrusted filename and folder as text", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    stubFetch({
      list: () => json(200, { documents: [doc("dx", `${evil}.pdf`, evil)], folders: [{ name: evil, count: 1 }] }),
    });
    const { container } = show();
    expect(await screen.findByText(`${evil}.pdf`)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("TaiLieu: admin lock", () => {
  it("hides upload and delete while locked", async () => {
    stubFetch();
    const { container } = show();
    await screen.findByText("NoiQuy_2026.docx");
    expect(fileInput(container)).toBeNull();
    expect(screen.queryByRole("button", { name: /^Xoá / })).toBeNull();
  });

  it("wrong password: aria-invalid, error text, nothing stored", async () => {
    const user = userEvent.setup();
    const api = stubFetch({ check: () => json(401, { detail: "Sai mật khẩu" }) });
    const { container } = show();
    await screen.findByText("NoiQuy_2026.docx");
    await unlockWith(user, "sai-mat-khau");

    const input = screen.getByLabelText("Mật khẩu quản trị");
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText(/Sai mật khẩu/)).toBeInTheDocument();
    expect(sessionStorage.getItem(ADMIN_KEY)).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(fileInput(container)).toBeNull();
    const [check] = api.checks();
    expect(check.method).toBe("POST");
    expect(new Headers(check.init?.headers).get("X-Admin-Password")).toBe("sai-mat-khau");
    expect(check.url.href).not.toContain("sai-mat-khau");
  });

  it("non-ASCII password: inline error, no request, nothing stored", async () => {
    const user = userEvent.setup();
    const api = stubFetch();
    const { container } = show();
    await screen.findByText("NoiQuy_2026.docx");
    await unlockWith(user, "mật-khẩu");

    const input = screen.getByLabelText("Mật khẩu quản trị");
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByText(/Mật khẩu chỉ dùng chữ không dấu/)).toBeInTheDocument();
    expect(api.checks()).toHaveLength(0);
    expect(sessionStorage.length).toBe(0);
    expect(fileInput(container)).toBeNull();
  });

  it("right password: stored only in sessionStorage, upload and delete appear; 'Khoá lại' clears it", async () => {
    const user = userEvent.setup();
    const api = stubFetch();
    const { container } = show();
    await screen.findByText("NoiQuy_2026.docx");
    await unlockWith(user, PW);

    await waitFor(() => expect(fileInput(container)).not.toBeNull());
    expect(sessionStorage.getItem(ADMIN_KEY)).toBe(PW);
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)!;
      expect(k).not.toContain(PW);
      expect(localStorage.getItem(k) ?? "").not.toContain(PW);
    }
    expect(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" })).toBeInTheDocument();
    expect(new Headers(api.checks()[0].init?.headers).get("X-Admin-Password")).toBe(PW);

    await user.click(screen.getByRole("button", { name: /Khoá lại/ }));
    expect(sessionStorage.getItem(ADMIN_KEY)).toBeNull();
    expect(fileInput(container)).toBeNull();
    expect(screen.queryByRole("button", { name: /^Xoá / })).toBeNull();
  });

  it("an admin request answered 401 clears sessionStorage and locks the UI", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(ADMIN_KEY, "mat-khau-da-doi");
    stubFetch({ remove: () => json(401, { detail: "Sai mật khẩu" }) });
    const { container } = show();
    await screen.findByText("NoiQuy_2026.docx");
    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    await user.click(screen.getByRole("button", { name: "Xoá file" }));

    await waitFor(() => expect(sessionStorage.getItem(ADMIN_KEY)).toBeNull());
    await waitFor(() => expect(fileInput(container)).toBeNull());
    expect(screen.queryByRole("button", { name: /^Xoá / })).toBeNull();
    expect(screen.getAllByRole("button", { name: /Mở khoá quản trị/ }).length).toBeGreaterThan(0);
  });
});

describe("TaiLieu: delete", () => {
  it("confirms inline, 'Huỷ' cancels, 'Xoá file' sends DELETE with the admin header", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(ADMIN_KEY, PW);
    const api = stubFetch();
    show();
    await screen.findByText("NoiQuy_2026.docx");

    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    expect(screen.getByRole("button", { name: "Xoá file" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Huỷ" }));
    expect(screen.queryByRole("button", { name: "Xoá file" })).toBeNull();
    expect(api.deletes()).toHaveLength(0);
    expect(screen.getByText("NoiQuy_2026.docx")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    await user.click(screen.getByRole("button", { name: "Xoá file" }));
    await waitFor(() => expect(api.deletes()).toHaveLength(1));
    const [del] = api.deletes();
    expect(del.url.pathname).toBe("/api/documents/d-ready");
    expect(new Headers(del.init?.headers).get("X-Admin-Password")).toBe(PW);
    await waitFor(() => expect(screen.queryByText("NoiQuy_2026.docx")).toBeNull());
  });

  it("keeps a deleted row hidden on the next poll even if the server still returns it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    sessionStorage.setItem(ADMIN_KEY, PW);
    const api = stubFetch({ list: () => json(200, { documents: [INDEXING, READY], folders: FOLDERS }) });
    show();
    await screen.findByText("NoiQuy_2026.docx");
    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    await user.click(screen.getByRole("button", { name: "Xoá file" }));
    await waitFor(() => expect(screen.queryByText("NoiQuy_2026.docx")).toBeNull());

    const before = api.lists().length;
    await act(() => vi.advanceTimersByTimeAsync(2100));
    await waitFor(() => expect(api.lists().length).toBeGreaterThan(before));
    expect(screen.getByText("QuyTrinhDuyet.pdf")).toBeInTheDocument();
    expect(screen.queryByText("NoiQuy_2026.docx")).toBeNull();
  });

  it("409 shows the server detail", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(ADMIN_KEY, PW);
    stubFetch({ remove: () => json(409, { detail: "File đang index, chờ xong rồi xoá" }) });
    show();
    await screen.findByText("NoiQuy_2026.docx");
    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    await user.click(screen.getByRole("button", { name: "Xoá file" }));
    expect(await screen.findByText(/File đang index, chờ xong rồi xoá/)).toBeInTheDocument();
    expect(sessionStorage.getItem(ADMIN_KEY)).toBe(PW);
  });

  it("404 drops the row", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(ADMIN_KEY, PW);
    stubFetch({ remove: () => json(404, { detail: "Không có tài liệu" }) });
    show();
    await screen.findByText("NoiQuy_2026.docx");
    await user.click(screen.getByRole("button", { name: "Xoá NoiQuy_2026.docx" }));
    await user.click(screen.getByRole("button", { name: "Xoá file" }));
    await waitFor(() => expect(screen.queryByText("NoiQuy_2026.docx")).toBeNull());
    expect(screen.getByText("HoaDon_Scan.pdf")).toBeInTheDocument();
  });
});

describe("TaiLieu: polling", () => {
  it("re-fetches every 2 s while a row is indexing and stops when none is", async () => {
    vi.useFakeTimers();
    let n = 0;
    const api = stubFetch({
      list: () => {
        n += 1;
        const d = n === 1 ? [INDEXING, READY] : [{ ...INDEXING, status: "ready" as const, chunk_count: 10 }, READY];
        return json(200, { documents: d, folders: FOLDERS });
      },
    });
    show();
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(api.lists()).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(1900));
    expect(api.lists()).toHaveLength(1);
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(api.lists()).toHaveLength(2);
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api.lists()).toHaveLength(2);
  });

  it("does not poll when nothing is indexing", async () => {
    vi.useFakeTimers();
    const api = stubFetch();
    show();
    await act(() => vi.advanceTimersByTimeAsync(0));
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api.lists()).toHaveLength(1);
  });

  it("stops polling after unmount", async () => {
    vi.useFakeTimers();
    const api = stubFetch({ list: () => json(200, { documents: [INDEXING], folders: FOLDERS }) });
    const view = show();
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(api.lists()).toHaveLength(1);
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.lists()).toHaveLength(1);
  });

  it("keeps the table when a later poll fails and polls again", async () => {
    vi.useFakeTimers();
    let n = 0;
    const api = stubFetch({
      list: () => {
        n += 1;
        return n === 2
          ? Promise.reject(new TypeError("Failed to fetch"))
          : json(200, { documents: [INDEXING], folders: FOLDERS });
      },
    });
    show();
    await act(() => vi.advanceTimersByTimeAsync(0));
    await act(() => vi.advanceTimersByTimeAsync(2100));
    expect(api.lists()).toHaveLength(2);
    expect(screen.getByText("QuyTrinhDuyet.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/Không kết nối được máy chủ/)).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(2100));
    expect(api.lists()).toHaveLength(3);
  });
});

describe("TaiLieu: folder filter in the URL", () => {
  it("passes ?thu-muc=A%26B as folder=A%26B and marks the tab", async () => {
    const user = userEvent.setup();
    const api = stubFetch({
      list: () => json(200, { documents: [doc("d1", "ab.pdf", "A&B")], folders: [{ name: "A&B", count: 1 }, ...FOLDERS] }),
    });
    show("/tai-lieu?thu-muc=A%26B");
    await screen.findByText("ab.pdf");
    const first = api.lists()[0];
    expect(first.url.search).toContain("folder=A%26B");
    expect(first.url.searchParams.get("folder")).toBe("A&B");
    expect(tab("A&B")).toHaveAttribute("aria-pressed", "true");
    expect(tab("Tất cả")).toHaveAttribute("aria-pressed", "false");

    await user.click(tab("Tất cả"));
    await waitFor(() => expect(screen.getByTestId("search").textContent).not.toContain("thu-muc"));
    expect(tab("Tất cả")).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(api.lists().at(-1)!.url.searchParams.get("folder") ?? "").toBe(""));
  });

  it("clicking a folder tab writes it to the URL", async () => {
    const user = userEvent.setup();
    stubFetch();
    show();
    await screen.findByText("NoiQuy_2026.docx");
    await user.click(tab("Kế toán"));
    await waitFor(() =>
      expect(new URLSearchParams(screen.getByTestId("search").textContent!).get("thu-muc")).toBe("Kế toán"),
    );
    expect(tab("Kế toán")).toHaveAttribute("aria-pressed", "true");
  });

  it("matches an NFD folder in the URL against the NFC tab", async () => {
    stubFetch();
    show(`/tai-lieu?thu-muc=${encodeURIComponent("Nhân sự".normalize("NFD"))}`);
    await screen.findByText("NoiQuy_2026.docx");
    expect(tab("Nhân sự")).toHaveAttribute("aria-pressed", "true");
  });

  it("sends a hostile folder value as one encoded parameter", async () => {
    const hostile = "../x' OR 1=1--&admin=1";
    const api = stubFetch({ list: () => json(200, { documents: [], folders: FOLDERS }) });
    show(`/tai-lieu?thu-muc=${encodeURIComponent(hostile)}`);
    await screen.findByText("Chưa có tài liệu nào");
    const { url } = api.lists()[0];
    expect(url.pathname).toBe("/api/documents");
    expect([...url.searchParams.keys()]).toEqual(["folder"]);
    expect(url.searchParams.get("folder")).toBe(hostile);
  });

  it("unknown folder shows the empty state with an 'Tất cả' tab", async () => {
    stubFetch({ list: () => json(200, { documents: [], folders: FOLDERS }) });
    show("/tai-lieu?thu-muc=Kh%C3%B4ng%20c%C3%B3");
    expect(await screen.findByText("Chưa có tài liệu nào")).toBeInTheDocument();
    expect(tab("Tất cả")).toBeInTheDocument();
  });
});

describe("TaiLieu: upload", () => {
  async function ready(path = "/tai-lieu?thu-muc=Nh%C3%A2n%20s%E1%BB%B1", h: Parameters<typeof stubFetch>[0] = {}) {
    sessionStorage.setItem(ADMIN_KEY, PW);
    const api = stubFetch(h);
    const view = show(path);
    await screen.findByText("NoiQuy_2026.docx");
    await waitFor(() => expect(api.configs().length).toBeGreaterThan(0));
    const input = await waitFor(() => {
      const el = fileInput(view.container);
      if (!el) throw new Error("no file input");
      return el;
    });
    return { api, view, input, user: userEvent.setup({ applyAccept: false }) };
  }

  it("folder field defaults to the filtered folder", async () => {
    await ready("/tai-lieu?thu-muc=K%E1%BA%BF%20to%C3%A1n");
    expect(screen.getByLabelText("Thư mục")).toHaveValue("Kế toán");
  });

  it("rejects a file over max_upload_mb without POST", async () => {
    const { api, input, user } = await ready(undefined, {
      config: () => json(200, { allow_external: false, providers: [], max_upload_mb: 1 }),
    });
    await user.upload(input, bigFile("big.pdf", 1024 * 1024 + 1));
    expect(await screen.findByText(/big\.pdf/)).toBeInTheDocument();
    expect(api.uploads()).toHaveLength(0);
  });

  it("accepts a file of exactly max_upload_mb", async () => {
    const { api, input, user } = await ready(undefined, {
      config: () => json(200, { allow_external: false, providers: [], max_upload_mb: 1 }),
    });
    await user.upload(input, bigFile("vua.pdf", 1024 * 1024));
    await waitFor(() => expect(api.uploads()).toHaveLength(1));
  });

  it("rejects a .exe without POST", async () => {
    const { api, input, user } = await ready();
    await user.upload(input, new File(["MZ"], "virus.exe", { type: "application/x-msdownload" }));
    expect(await screen.findByText(/virus\.exe/)).toBeInTheDocument();
    expect(api.uploads()).toHaveLength(0);
  });

  it("rejects an empty folder without POST", async () => {
    const { api, input, user } = await ready("/tai-lieu");
    const folder = screen.getByLabelText("Thư mục");
    await user.clear(folder);
    await user.upload(input, pdf("QuyDinh.pdf"));
    await waitFor(() =>
      expect(screen.queryByText(/QuyDinh\.pdf/) !== null || folder.getAttribute("aria-invalid") === "true").toBe(true),
    );
    expect(api.uploads()).toHaveLength(0);
  });

  it("posts FormData with file and folder and the admin header, then reloads the list", async () => {
    const { api, input, user } = await ready();
    const before = api.lists().length;
    const folder = screen.getByLabelText("Thư mục");
    await user.clear(folder);
    await user.type(folder, "Phòng Kế hoạch");
    await user.upload(input, pdf("QuyDinh.pdf"));
    await waitFor(() => expect(api.uploads()).toHaveLength(1));
    const [up] = api.uploads();
    const body = up.init?.body;
    expect(body).toBeInstanceOf(FormData);
    const fd = body as FormData;
    expect((fd.get("file") as File).name).toBe("QuyDinh.pdf");
    expect(fd.get("folder")).toBe("Phòng Kế hoạch");
    expect(new Headers(up.init?.headers).get("X-Admin-Password")).toBe(PW);
    await waitFor(() => expect(api.lists().length).toBeGreaterThan(before));
  });

  it.each([
    [409, "File cùng tên đang được index"],
    [413, "File vượt quá 20 MB"],
  ])("shows the server detail on %i", async (status, detail) => {
    const { input, user } = await ready(undefined, { upload: () => json(status, { detail }) });
    await user.upload(input, pdf("QuyDinh.pdf"));
    expect(await screen.findByText(new RegExp(detail))).toBeInTheDocument();
  });
});

describe("TaiLieu: multiple files", () => {
  async function ready(upload: H) {
    sessionStorage.setItem(ADMIN_KEY, PW);
    const api = stubFetch({ upload });
    const view = show("/tai-lieu?thu-muc=Nh%C3%A2n%20s%E1%BB%B1");
    await screen.findByText("NoiQuy_2026.docx");
    await waitFor(() => expect(api.configs().length).toBeGreaterThan(0));
    const input = await waitFor(() => {
      const el = fileInput(view.container);
      if (!el) throw new Error("no file input");
      return el;
    });
    return { api, view, input, user: userEvent.setup({ applyAccept: false }) };
  }
  const names = (api: ReturnType<typeof stubFetch>) =>
    api.uploads().map((u) => ((u.init!.body as FormData).get("file") as File).name);

  it("sends files one after another, in order", async () => {
    const first = deferred<Response>();
    let n = 0;
    const { api, input, user } = await ready(() => {
      n += 1;
      return n === 1 ? first.promise : json(202, doc("d-b", "b.docx", "Nhân sự", { status: "indexing" }));
    });
    await user.upload(input, [pdf("a.pdf"), new File(["PK"], "b.docx")]);
    await waitFor(() => expect(api.uploads()).toHaveLength(1));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(api.uploads()).toHaveLength(1);
    await act(async () => first.resolve(json(202, doc("d-a", "a.pdf", "Nhân sự", { status: "indexing" }))));
    await waitFor(() => expect(api.uploads()).toHaveLength(2));
    expect(names(api)).toEqual(["a.pdf", "b.docx"]);
  });

  it("keeps sending after a 409 and shows the error with the first file's name", async () => {
    let n = 0;
    const { api, input, user } = await ready(() => {
      n += 1;
      return n === 1
        ? json(409, { detail: "File cùng tên đang được index" })
        : json(202, doc("d-b", "b.pdf", "Nhân sự", { status: "indexing" }));
    });
    await user.upload(input, [pdf("a.pdf"), pdf("b.pdf")]);
    await waitFor(() => expect(api.uploads()).toHaveLength(2));
    const msg = await screen.findByText(/File cùng tên đang được index/);
    expect(msg.closest("li, p, div")?.textContent).toContain("a.pdf");
    expect(names(api)).toEqual(["a.pdf", "b.pdf"]);
  });

  it("skips an invalid file in the selection and still sends the valid ones", async () => {
    const { api, input, user } = await ready(() => json(202, doc("d-n", "x.pdf", "Nhân sự", { status: "indexing" })));
    await user.upload(input, [pdf("a.pdf"), new File(["MZ"], "virus.exe"), new File(["PK"], "c.xlsx")]);
    await waitFor(() => expect(api.uploads()).toHaveLength(2));
    expect(names(api)).toEqual(["a.pdf", "c.xlsx"]);
    expect(screen.getByText(/virus\.exe/)).toBeInTheDocument();
  });

  it("stops the upload loop after unmount", async () => {
    const first = deferred<Response>();
    const { api, view, input, user } = await ready(() => first.promise);
    await user.upload(input, [pdf("a.pdf"), pdf("b.pdf")]);
    await waitFor(() => expect(api.uploads()).toHaveLength(1));
    view.unmount();
    await act(async () => first.resolve(json(202, doc("d-a", "a.pdf", "Nhân sự", { status: "indexing" }))));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(api.uploads()).toHaveLength(1);
  });
});
