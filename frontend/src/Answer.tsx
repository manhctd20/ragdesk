import { FileSpreadsheet, FileText, Lock, LockOpen, CircleAlert } from "lucide-react";
import { Link } from "react-router";
import type { Mode, AskResult, Source } from "./api";
import { PROVIDER_LABEL, highlight, splitCitations, whereLabel } from "./format";

function FileIcon({ type }: { type: Source["meta"]["file_type"] }) {
  const Icon = type === "xlsx" ? FileSpreadsheet : FileText;
  return <Icon className="ic" aria-hidden="true" />;
}

function Card({ s }: { s: Source }) {
  const where = whereLabel(s.meta);
  return (
    <div className="src">
      <FileIcon type={s.meta.file_type} />
      <div>
        <b>{s.meta.filename}</b>
        {where && <span className="where">{where}</span>}
      </div>
      <p>
        {highlight(s.text, s.matched).map((seg, i) =>
          seg.hit ? <mark key={i} className="hl">{seg.text}</mark> : seg.text,
        )}
      </p>
    </div>
  );
}

interface Props { mode: Mode; result: AskResult; question?: string; provider?: string | null }

export default function Answer({ mode, result, question, provider }: Props) {
  const { answer, sources, llm_error, message, query } = result;
  const external = mode === "external";
  const ModeIcon = external ? LockOpen : Lock;
  const who = provider ? ` (${PROVIDER_LABEL[provider] ?? provider})` : "";
  // External answers list sources as chips, also while text is still streaming; cards only when no answer is coming.
  const chips = external && (answer || !llm_error);
  return (
    <div className="answer">
      {query && query !== question && <p className="understood">Hiểu là: {query}</p>}
      <div className="mode">
        <ModeIcon className="ic" aria-hidden="true" />
        {external ? `AI ngoài${who}: câu trả lời tổng hợp từ các đoạn` : "Chỉ nội bộ: các đoạn liên quan nhất"}
      </div>
      {message && (
        <div className="notice">
          <p>{message}</p>
          <Link to="/tai-lieu">Mở trang Tài liệu</Link>
        </div>
      )}
      {answer && (
        <p className="text">
          {splitCitations(answer, sources.length).map((p, i) =>
            typeof p === "number" ? <span key={i} className="cite">{p}</span> : p,
          )}
        </p>
      )}
      {llm_error && (
        <p className="err" role="alert">
          <CircleAlert className="ic" aria-hidden="true" />
          {llm_error}
        </p>
      )}
      {chips ? (
        sources.length > 0 && (
          <div className="chips">
            {sources.map((s, i) => (
              <span key={s.id} className="chip">
                <span className="n">{i + 1}</span>
                {s.meta.filename}
              </span>
            ))}
          </div>
        )
      ) : (
        sources.map((s) => <Card key={s.id} s={s} />)
      )}
    </div>
  );
}
