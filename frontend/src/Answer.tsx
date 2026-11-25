import { FileSpreadsheet, FileText, Lock, LockOpen, CircleAlert } from "lucide-react";
import { Link } from "react-router";
import type { Mode, AskResult, Source } from "./api";
import { highlight, splitCitations, whereLabel } from "./format";

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

export default function Answer({ mode, result }: { mode: Mode; result: AskResult }) {
  const { answer, sources, llm_error, message } = result;
  const external = mode === "external";
  const ModeIcon = external ? LockOpen : Lock;
  return (
    <div className="answer">
      <div className="mode">
        <ModeIcon className="ic" aria-hidden="true" />
        {external ? "AI ngoài: câu trả lời tổng hợp từ các đoạn" : "Chỉ nội bộ: các đoạn liên quan nhất"}
      </div>
      {message && (
        <div className="notice">
          <p>{message}</p>
          <Link to="/tai-lieu">Mở trang Tài liệu</Link>
        </div>
      )}
      {llm_error && (
        <p className="err" role="alert">
          <CircleAlert className="ic" aria-hidden="true" />
          {llm_error}
        </p>
      )}
      {answer && (
        <>
          <p className="text">
            {splitCitations(answer, sources.length).map((p, i) =>
              typeof p === "number" ? <span key={i} className="cite">{p}</span> : p,
            )}
          </p>
          <div className="chips">
            {sources.map((s, i) => (
              <span key={s.id} className="chip">
                <span className="n">{i + 1}</span>
                {s.meta.filename}
              </span>
            ))}
          </div>
        </>
      )}
      {!answer && sources.map((s) => <Card key={s.id} s={s} />)}
    </div>
  );
}
