import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import Answer from "./Answer";
import type { AskResult, Mode, Source } from "./api";

const EVIL = "<img src=x onerror=alert(1)>";

function src(n: number, over: Partial<Source> = {}, meta: Partial<Source["meta"]> = {}): Source {
  return {
    id: `doc${n}:0`,
    text: `Người lao động phải gửi đơn ít nhất 03 ngày làm việc trước ngày nghỉ (${n})`,
    meta: { doc_id: `doc${n}`, filename: `TaiLieu${n}.pdf`, folder: "Nhân sự", file_type: "pdf", page: n, ...meta },
    score: 0.03,
    matched: ["gửi", "đơn"],
    ...over,
  };
}

function result(over: Partial<AskResult>): AskResult {
  return { answer: null, sources: [], llm_error: null, message: null, ...over };
}

function show(mode: Mode, r: AskResult, extra: { question?: string; provider?: string | null } = {}) {
  return render(
    <MemoryRouter>
      <Answer mode={mode} result={r} {...extra} />
    </MemoryRouter>,
  );
}

describe("Answer", () => {
  it("internal: one card per source with filename, location and marked terms", () => {
    const sources = [
      src(1, {}, { page: 7 }),
      src(2, { text: "Loại nghỉ: Phép năm; Báo trước: 3 ngày", matched: ["báo"] }, {
        filename: "BangNghiPhep.xlsx",
        file_type: "xlsx",
        page: undefined,
        sheet: "Quy định",
        row: 12,
      }),
    ];
    const { container } = show("internal", result({ sources }));
    expect(screen.getByText(/TaiLieu1\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/Trang 7/)).toBeInTheDocument();
    expect(screen.getByText(/BangNghiPhep\.xlsx/)).toBeInTheDocument();
    expect(screen.getByText(/Sheet Quy định, dòng 12/)).toBeInTheDocument();
    const marks = Array.from(container.querySelectorAll("mark")).map((m) => m.textContent);
    expect(marks).toEqual(["gửi", "đơn", "Báo"]);
  });

  it("external: citation label and source chip with filename", () => {
    const { container } = show(
      "external",
      result({ answer: "Cần trưởng phòng duyệt [1].", sources: [src(1, {}, { filename: "QuyTrinhDuyet.pdf" })] }),
    );
    expect(screen.getByText(/Cần trưởng phòng duyệt/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("[1]");
    const cites = screen.getAllByText("1");
    expect(cites.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/QuyTrinhDuyet\.pdf/).length).toBeGreaterThanOrEqual(1);
  });

  it("external with llm_error: shows the error and still shows source cards", () => {
    const { container } = show(
      "external",
      result({ llm_error: "Không gọi được AI ngoài (APIConnectionError)", sources: [src(1, {}, { filename: "NoiQuy.docx" })] }),
    );
    expect(screen.getByText(/Không gọi được AI ngoài \(APIConnectionError\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/NoiQuy\.docx/).length).toBeGreaterThanOrEqual(1);
    expect(container.textContent).toContain("phải gửi đơn ít nhất 03 ngày");
  });

  it("message with no sources: shows the message and a link to /tai-lieu", () => {
    show("internal", result({ message: "Chưa có tài liệu nào" }));
    expect(screen.getByText(/Chưa có tài liệu nào/)).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.some((a) => a.getAttribute("href") === "/tai-lieu")).toBe(true);
  });

  it("shows 'Hiểu là' only when query differs from the question", () => {
    const answer = "Trưởng phòng duyệt [1].";
    const sources = [src(1)];
    const view = show("external", result({ answer, sources, query: "Nghỉ phép năm ai duyệt?" }), { question: "Thế ai duyệt?" });
    expect(screen.getByText("Hiểu là: Nghỉ phép năm ai duyệt?")).toBeInTheDocument();
    view.unmount();

    const same = show("external", result({ answer, sources, query: "Thế ai duyệt?" }), { question: "Thế ai duyệt?" });
    expect(screen.queryByText(/Hiểu là/)).toBeNull();
    same.unmount();

    show("external", result({ answer, sources, query: null }), { question: "Thế ai duyệt?" });
    expect(screen.queryByText(/Hiểu là/)).toBeNull();
  });

  it("label names the provider", () => {
    const r = result({ answer: "Trả lời [1].", sources: [src(1)] });
    const view = show("external", r, { provider: "claude" });
    expect(screen.getByText("AI ngoài (Claude): câu trả lời tổng hợp từ các đoạn")).toBeInTheDocument();
    view.unmount();

    show("external", r, { provider: "openai" });
    expect(screen.getByText("AI ngoài (OpenAI): câu trả lời tổng hợp từ các đoạn")).toBeInTheDocument();
  });

  describe("low relevance", () => {
    const NOTICE = "Không tìm thấy đoạn nào đủ liên quan";

    it("low relevance shows the notice and hides cards until expanded", async () => {
      const user = userEvent.setup();
      show("internal", result({ low_relevance: true, sources: [src(1, {}, { filename: "Gan1.pdf" })] }));
      expect(screen.getByText(NOTICE)).toBeInTheDocument();
      const btn = screen.getByRole("button", { name: "Xem các đoạn gần nhất" });
      expect(btn).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText(/Gan1\.pdf/)).toBeNull();
      await user.click(btn);
      expect(btn).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText(/Gan1\.pdf/)).toBeInTheDocument();
      await user.click(btn);
      expect(screen.queryByText(/Gan1\.pdf/)).toBeNull();
    });

    it("external: no answer text and no chips, cards only after expanding", async () => {
      const user = userEvent.setup();
      const { container } = show("external", result({ low_relevance: true, sources: [src(1, {}, { filename: "Gan1.pdf" })] }));
      expect(screen.getByText(NOTICE)).toBeInTheDocument();
      expect(container.querySelector(".chip, .text")).toBeNull();
      expect(screen.queryByText(/Gan1\.pdf/)).toBeNull();
      await user.click(screen.getByRole("button", { name: "Xem các đoạn gần nhất" }));
      expect(screen.getByText(/Gan1\.pdf/)).toBeInTheDocument();
      expect(container.querySelector(".chip")).toBeNull();
    });

    it("old turns without low_relevance render as before", () => {
      show("internal", result({ sources: [src(1, {}, { filename: "Gan1.pdf" })] }));
      expect(screen.queryByText(NOTICE)).toBeNull();
      expect(screen.queryByRole("button", { name: "Xem các đoạn gần nhất" })).toBeNull();
      expect(screen.getByText(/Gan1\.pdf/)).toBeInTheDocument();
    });
  });

  describe("untrusted text is never rendered as HTML", () => {
    it("external answer and filename with an <img> payload stay literal text", () => {
      const { container } = show(
        "external",
        result({
          answer: `Trả lời ${EVIL} [1]`,
          sources: [src(1, { text: `Đoạn ${EVIL} gửi đơn` }, { filename: `${EVIL}.pdf` })],
        }),
      );
      expect(container.querySelector("img")).toBeNull();
      expect(container.querySelector("[onerror]")).toBeNull();
      expect(container.textContent).toContain(`Trả lời ${EVIL}`);
      expect(container.textContent).toContain(`${EVIL}.pdf`);
    });

    it("internal chunk text and filename with an <img> payload stay literal text", () => {
      const { container } = show(
        "internal",
        result({ sources: [src(1, { text: `${EVIL} gửi` }, { filename: `${EVIL}.pdf` })] }),
      );
      expect(container.querySelector("img")).toBeNull();
      expect(container.textContent).toContain(`${EVIL} gửi`);
      expect(container.textContent).toContain(`${EVIL}.pdf`);
    });

    it("llm_error with an <img> payload stays literal text", () => {
      const { container } = show("external", result({ llm_error: EVIL, sources: [src(1)] }));
      expect(container.querySelector("img")).toBeNull();
      expect(container.textContent).toContain(EVIL);
    });

    it("markdown in the answer is shown verbatim", () => {
      const { container } = show(
        "external",
        result({ answer: "Cần **đậm** và # tiêu đề [1]", sources: [src(1)] }),
      );
      expect(container.textContent).toContain("**đậm**");
      expect(container.textContent).toContain("# tiêu đề");
      expect(screen.getByText(/\*\*đậm\*\*/).querySelector("strong, b")).toBeNull();
      expect(screen.queryByRole("heading", { name: /tiêu đề/ })).toBeNull();
    });
  });
});
