import { ArrowUp, Lock, LockOpen, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import Answer from "./Answer";
import { ApiError, ask, getConfig, type Config, type Mode } from "./api";
import { newId, type Conversation, type Turn } from "./history";

interface Props { conversations: Conversation[]; onSave: (c: Conversation) => void }

export default function Chat({ conversations, onSave }: Props) {
  const paramId = useParams().id;
  const existing = paramId ? conversations.find((c) => c.id === paramId) : undefined;
  const navigate = useNavigate();
  const [id] = useState(() => existing?.id ?? newId());
  const [createdAt] = useState(() => existing?.createdAt ?? new Date().toISOString());
  const [turns, setTurns] = useState<Turn[]>(existing?.turns ?? []);
  const [config, setConfig] = useState<Config | null>(null);
  const [external, setExternal] = useState(false);
  const [navTo, setNavTo] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<{ question: string; mode: Mode } | null>(null);
  const [failed, setFailed] = useState<{ question: string; mode: Mode; message: string } | null>(null);
  const mounted = useRef(true);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mounted.current = true;
    getConfig().then((c) => mounted.current && setConfig(c), () => {});
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (navTo && conversations.some((c) => c.id === navTo)) navigate(`/c/${navTo}`, { replace: true });
  }, [navTo, conversations, navigate]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [turns, pending, failed]);

  if (paramId && !existing) return <p className="notice-page">Không tìm thấy cuộc hỏi này</p>;

  async function run(question: string, mode: Mode) {
    setFailed(null);
    setPending({ question, mode });
    try {
      const result = await ask(question, mode);
      const now = new Date().toISOString();
      const next = [...turns, { question, mode, askedAt: now, result }];
      if (paramId) {
        setTurns(next);
        setPending(null);
      } else setNavTo(id);
      onSave({ id, title: next[0].question.slice(0, 60), createdAt, updatedAt: now, turns: next });
    } catch (e) {
      setPending(null);
      setFailed({ question, mode, message: e instanceof ApiError ? e.message : "Có lỗi xảy ra" });
    }
  }

  const question = text.trim();
  const busy = pending !== null;
  const canSend = question !== "" && !busy;

  function submit() {
    if (!canSend) return;
    const mode: Mode = external ? "external" : "internal";
    setText("");
    setExternal(false);
    void run(question, mode);
  }

  const allow = config?.allow_external === true;
  const ToggleIcon = external ? LockOpen : Lock;
  const LOCKED = "Quản trị chưa cho phép gửi ra ngoài";
  const SENDS_OUT = "Câu hỏi và các đoạn liên quan sẽ gửi tới AI ngoài";
  const hint = config && !allow ? LOCKED : external ? SENDS_OUT : "Tài liệu không rời khỏi máy chủ";

  function onToggle() {
    if (!config) return;
    if (!allow) return setToast(LOCKED);
    if (!external) setToast(SENDS_OUT);
    setExternal(!external);
  }

  return (
    <div className="chat">
      <div className="thread" role="region" aria-label="Cuộc hỏi" tabIndex={0}>
        {turns.map((t) => (
          <section key={t.askedAt} className="turn">
            <div className="q">{t.question}</div>
            <Answer mode={t.mode} result={t.result} />
          </section>
        ))}
        {(pending ?? failed) && (
          <section className="turn">
            <div className="q">{(pending ?? failed)!.question}</div>
            {pending && (
              <p className="wait" role="status">
                {pending.mode === "external" ? "Đang viết câu trả lời…" : "Đang tìm…"}
              </p>
            )}
            {failed && (
              <div className="err" role="alert">
                <p>{failed.message}</p>
                <button type="button" className="btn" onClick={() => void run(failed.question, failed.mode)}>
                  <RefreshCw className="ic" aria-hidden="true" />
                  Thử lại
                </button>
              </div>
            )}
          </section>
        )}
        <div ref={end} />
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          className="ta"
          rows={1}
          value={text}
          placeholder="Hỏi về tài liệu nội bộ…"
          aria-label="Câu hỏi"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-bar">
          <button
            type="button"
            className="toggle"
            aria-pressed={external}
            aria-disabled={!allow}
            onClick={onToggle}
          >
            <ToggleIcon className="ic" aria-hidden="true" />
            {external ? "AI ngoài" : "Chỉ nội bộ"}
          </button>
          <span className="hint">{hint}</span>
          <button type="submit" className="send" aria-label="Gửi câu hỏi" disabled={!canSend}>
            <ArrowUp className="ic" aria-hidden="true" />
          </button>
        </div>
      </form>
      <div className="toast" role="status">{toast}</div>
    </div>
  );
}
