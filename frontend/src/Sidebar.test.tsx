import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import { THEME_KEY, applyStoredTheme, type Conversation } from "./history";

function stubMatchMedia(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query.includes("dark"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
}

function conv(id: string, title: string, updatedAt: Date): Conversation {
  const iso = updatedAt.toISOString();
  return {
    id,
    title,
    createdAt: iso,
    updatedAt: iso,
    turns: [
      {
        question: title,
        mode: "internal",
        askedAt: iso,
        result: { answer: null, sources: [], llm_error: null, message: "Chưa có tài liệu nào" },
      },
    ],
  };
}

function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(12, 0, 0, 0);
  return d;
}

const TODAY = conv("hom-nay-1", "Quy trình nghỉ phép", new Date());
const OLD = conv("cu-hon-1", "Định mức công tác phí", daysAgo(30));

function show(path: string, conversations: Conversation[] = [TODAY, OLD]) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar conversations={conversations} />
    </MemoryRouter>,
  );
}

const before = (a: Node, b: Node) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;

beforeEach(() => stubMatchMedia(false));

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("Sidebar", () => {
  it("toggles theme, persists it and applyStoredTheme restores it", async () => {
    const user = userEvent.setup();
    show("/");
    await user.click(screen.getByRole("button", { name: "Chuyển sang giao diện tối" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).not.toBeNull();
    expect(screen.getByRole("button", { name: "Chuyển sang giao diện sáng" })).toBeInTheDocument();

    delete document.documentElement.dataset.theme;
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");

    await user.click(screen.getByRole("button", { name: "Chuyển sang giao diện sáng" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    delete document.documentElement.dataset.theme;
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("offers the light theme first when the OS prefers dark and nothing is stored", () => {
    stubMatchMedia(true);
    show("/");
    expect(screen.getByRole("button", { name: "Chuyển sang giao diện sáng" })).toBeInTheDocument();
  });

  it("applyStoredTheme leaves data-theme unset when nothing is stored", () => {
    applyStoredTheme();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("applyStoredTheme does not throw when localStorage is unavailable", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => applyStoredTheme()).not.toThrow();
    spy.mockRestore();
  });

  it("lists conversations under their day-group headings with links to /c/:id", () => {
    show("/");
    const today = screen.getByText("Hôm nay");
    const older = screen.getByText("Cũ hơn");
    const a = screen.getByRole("link", { name: /Quy trình nghỉ phép/ });
    const b = screen.getByRole("link", { name: /Định mức công tác phí/ });
    expect(a).toHaveAttribute("href", "/c/hom-nay-1");
    expect(b).toHaveAttribute("href", "/c/cu-hon-1");
    expect(before(today, a)).toBe(true);
    expect(before(a, older)).toBe(true);
    expect(before(older, b)).toBe(true);
    expect(screen.queryByText("Hôm qua")).toBeNull();
    expect(screen.queryByText("Tuần trước")).toBeNull();
  });

  it("has a 'Cuộc hỏi mới' link to /", () => {
    show("/c/hom-nay-1");
    expect(screen.getByRole("link", { name: /Cuộc hỏi mới/ })).toHaveAttribute("href", "/");
  });

  it("marks the open conversation as current", () => {
    show("/c/hom-nay-1");
    expect(screen.getByRole("link", { name: /Quy trình nghỉ phép/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Định mức công tác phí/ })).not.toHaveAttribute("aria-current");
  });

  it("on /tai-lieu still shows history and marks 'Tài liệu' current", () => {
    show("/tai-lieu");
    expect(screen.getByRole("link", { name: /Quy trình nghỉ phép/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Định mức công tác phí/ })).toBeInTheDocument();
    const docs = screen.getByRole("link", { name: /Tài liệu/ });
    expect(docs).toHaveAttribute("href", "/tai-lieu");
    expect(docs).toHaveAttribute("aria-current", "page");
  });

  it("renders conversation titles as text, not HTML", () => {
    const { container } = show("/", [conv("x", "<img src=x onerror=alert(1)>", new Date())]);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("link", { name: /<img src=x/ })).toBeInTheDocument();
  });
});
