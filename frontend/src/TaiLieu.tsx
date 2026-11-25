import { Check, CircleAlert, FileSpreadsheet, FileText, LoaderCircle, Lock, LockOpen, RefreshCw, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useSearchParams } from "react-router";
import {
  ApiError, deleteDocument, getConfig, isUnlocked, listDocuments, lock, uploadDocument, unlock,
  type Config, type Doc, type Folder,
} from "./api";
import { formatWhen } from "./format";

const POLL_MS = 2000;
const EXT = /\.(pdf|docx|xlsx)$/i;
const DEFAULT_FOLDER = "Chung";

interface Listing { folder: string; documents: Doc[]; folders: Folder[] }

function Status({ d }: { d: Doc }) {
  if (d.status === "error")
    return (
      <span className="st err">
        <CircleAlert className="ic" aria-hidden="true" />
        {d.error ?? "Lỗi khi index"}
      </span>
    );
  if (d.status === "indexing") {
    const known = d.progress_total > 0;
    return (
      <div className="prog">
        <span className="st">
          <LoaderCircle className="ic" aria-hidden="true" />
          {known ? `Đang index, đoạn ${d.progress_done}/${d.progress_total}` : "Đang index"}
        </span>
        {known && (
          <span className="bar">
            <i style={{ "--p": d.progress_done / d.progress_total } as React.CSSProperties} />
          </span>
        )}
      </div>
    );
  }
  return (
    <span className="st">
      <Check className="ic" aria-hidden="true" />
      Sẵn sàng
    </span>
  );
}

export default function TaiLieu() {
  const [params, setParams] = useSearchParams();
  const folder = (params.get("thu-muc") ?? "").normalize("NFC");

  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const removedRef = useRef(removed);
  useEffect(() => {
    removedRef.current = removed;
  }, [removed]);
  const dataRef = useRef<Listing | null>(null);
  const mounted = useRef(true);

  const [config, setConfig] = useState<Config | null>(null);
  const [admin, setAdmin] = useState(isUnlocked);
  const [unlockOpen, setUnlockOpen] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [checking, setChecking] = useState(false);

  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [folderInput, setFolderInput] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    mounted.current = true;
    getConfig().then((c) => mounted.current && setConfig(c), () => {});
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      try {
        const d = await listDocuments(folder);
        if (!alive) return;
        const next = { folder, ...d };
        dataRef.current = next;
        setData(next);
        setError(null);
        setRemoved((prev) => new Set([...prev].filter((id) => d.documents.some((x) => x.id === id))));
        if (d.documents.some((x) => x.status === "indexing" || removedRef.current.has(x.id))) timer = setTimeout(run, POLL_MS);
      } catch (e) {
        if (!alive) return;
        if (dataRef.current?.folder === folder) timer = setTimeout(run, POLL_MS);
        else setError(e instanceof ApiError ? e.message : "Có lỗi xảy ra");
      }
    };
    void run();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [folder, reload]);

  const current = data?.folder === folder ? data : null;
  const docs = current?.documents.filter((d) => !removed.has(d.id)) ?? [];
  const maxMb = config?.max_upload_mb ?? 20;

  function selectFolder(name: string) {
    setError(null);
    setParams(name ? { "thu-muc": name } : {});
  }

  function lostAdmin(e: unknown) {
    if (e instanceof ApiError && e.status === 401) setAdmin(false);
  }

  async function submitUnlock(e: React.FormEvent) {
    e.preventDefault();
    if (!/^[\x20-\x7e]*$/.test(pw)) {
      setPwError("Mật khẩu chỉ dùng chữ không dấu");
      return;
    }
    setChecking(true);
    try {
      await unlock(pw);
      setAdmin(true);
      setUnlockOpen(false);
      setPw("");
      setPwError(null);
    } catch (err) {
      setPwError(
        err instanceof ApiError && err.status === 401 ? "Sai mật khẩu. Hỏi người quản trị máy chủ." : (err as Error).message,
      );
    } finally {
      setChecking(false);
    }
  }

  async function remove(id: string) {
    setConfirmId(null);
    setNotice(null);
    try {
      await deleteDocument(id);
      setRemoved((s) => new Set(s).add(id));
      setReload((n) => n + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setRemoved((s) => new Set(s).add(id));
      else {
        lostAdmin(e);
        setNotice((e as Error).message);
      }
    }
  }

  async function upload(files: File[]) {
    if (files.length === 0 || uploading) return;
    const dest = (folderInput ?? folder).trim() || DEFAULT_FOLDER;
    setUploadErrors([]);
    setUploading(true);
    const errors: string[] = [];
    for (const f of files) {
      let problem: string | null = null;
      if (!EXT.test(f.name)) problem = "Chỉ nhận file .pdf, .docx, .xlsx";
      else if (f.size > maxMb * 1024 * 1024) problem = `File vượt quá ${maxMb} MB`;
      else {
        try {
          await uploadDocument(f, dest);
        } catch (e) {
          if (!mounted.current) return;
          problem = (e as Error).message;
          lostAdmin(e);
          if (e instanceof ApiError && e.status === 401) {
            errors.push(`${f.name}: ${problem}`);
            setUploadErrors([...errors]);
            break;
          }
        }
      }
      if (!mounted.current) return;
      if (problem) {
        errors.push(`${f.name}: ${problem}`);
        setUploadErrors([...errors]);
      }
    }
    setUploading(false);
    setFolderInput(null);
    setReload((n) => n + 1);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    void upload(Array.from(e.dataTransfer.files));
  }

  const folders = data?.folders ?? [];
  const total = folders.reduce((n, f) => n + f.count, 0);
  const tabs = [{ name: "", label: "Tất cả", count: total }, ...folders.map((f) => ({ name: f.name, label: f.name, count: f.count }))];

  return (
    <>
      <div className="head">
        <h1>Tài liệu</h1>
        {current && <span className="count">{docs.length} file</span>}
        {admin ? (
          <button type="button" className="btn ghost" onClick={() => { lock(); setAdmin(false); setConfirmId(null); }}>
            <Lock className="ic" aria-hidden="true" />
            Khoá lại
          </button>
        ) : unlockOpen ? (
          <form className="unlock" onSubmit={submitUnlock}>
            <div className="field">
              <label htmlFor="pw">Mật khẩu quản trị</label>
              <input
                className="input"
                id="pw"
                type="password"
                value={pw}
                autoComplete="off"
                aria-invalid={pwError !== null}
                aria-describedby="pw-h"
                onChange={(e) => { setPw(e.target.value); setPwError(null); }}
              />
              <span className={pwError ? "help err" : "help"} id="pw-h">{pwError}</span>
            </div>
            <button type="submit" className="btn primary unlock-btn" disabled={checking}>
              <LockOpen className="ic" aria-hidden="true" />
              Mở khoá
            </button>
            <button type="button" className="btn ghost unlock-btn" onClick={() => { setUnlockOpen(false); setPw(""); setPwError(null); }}>
              Huỷ
            </button>
          </form>
        ) : (
          <button type="button" className="btn ghost" onClick={() => setUnlockOpen(true)}>
            <LockOpen className="ic" aria-hidden="true" />
            Mở khoá quản trị
          </button>
        )}
      </div>

      {admin && (
        <div className="drop" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
          <div className="drop-txt">
            <Upload className="ic" aria-hidden="true" />
            <div>
              Kéo file vào đây hoặc chọn file
              <small>Word, PDF, Excel. Tối đa {maxMb} MB mỗi file.</small>
            </div>
          </div>
          <div className="drop-act">
            <div className="field">
              <label htmlFor="fd">Thư mục</label>
              <input
                className="input"
                id="fd"
                list="folders"
                placeholder={`Để trống: ${DEFAULT_FOLDER}`}
                value={folderInput ?? folder}
                onChange={(e) => setFolderInput(e.target.value)}
              />
              <datalist id="folders">
                {folders.map((f) => <option key={f.name} value={f.name} />)}
              </datalist>
            </div>
            <button type="button" className="btn primary" disabled={uploading} onClick={() => fileInput.current?.click()}>
              <Upload className="ic" aria-hidden="true" />
              Chọn file
            </button>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept=".pdf,.docx,.xlsx"
              multiple
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = "";
                void upload(files);
              }}
            />
          </div>
        </div>
      )}

      {uploadErrors.length > 0 && (
        <ul className="errlist" role="alert">
          {uploadErrors.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      )}
      {notice && <p className="help err" role="alert">{notice}</p>}

      <div className="filters" role="group" aria-label="Lọc theo thư mục">
        {tabs.map((t) => (
          <button
            key={t.name}
            type="button"
            className="tab"
            aria-pressed={t.name.normalize("NFC") === folder}
            onClick={() => selectFolder(t.name)}
          >
            {t.label}
            <span className="n">{t.count}</span>
          </button>
        ))}
      </div>

      {!current && error && (
        <div className="failed">
          <strong>Không tải được danh sách</strong>
          <p>{error}</p>
          <button type="button" className="btn" onClick={() => { setError(null); setReload((n) => n + 1); }}>
            <RefreshCw className="ic" aria-hidden="true" />
            Thử lại
          </button>
        </div>
      )}
      {!current && !error && (
        <div aria-busy="true">
          <span className="visually-hidden">Đang tải</span>
          {[0, 1, 2, 3].map((i) => <span key={i} className="sk sk-row" />)}
        </div>
      )}
      {current && docs.length === 0 && (
        <div className="empty">
          <strong>Chưa có tài liệu nào</strong>
          <p>{admin ? "Chọn file ở khung phía trên để tải lên." : "Mở khoá quản trị để tải tài liệu lên."}</p>
        </div>
      )}
      {current && docs.length > 0 && (
        <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Tên file</th>
                <th>Thư mục</th>
                <th className="num hide-sm">Số đoạn</th>
                <th className="hide-sm">Cập nhật</th>
                <th>Trạng thái</th>
                <th><span className="visually-hidden">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) =>
                confirmId === d.id ? (
                  <tr key={d.id} className="row-confirm">
                    <td colSpan={6}>
                      <div className="confirm">
                        <span>Xoá <b>{d.filename}</b>? Các đoạn của file này sẽ không còn được tìm thấy.</span>
                        <button type="button" className="btn" onClick={() => setConfirmId(null)}>Huỷ</button>
                        <button type="button" className="btn danger" onClick={() => void remove(d.id)}>Xoá file</button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={d.id}>
                    <td>
                      <span className="fname">
                        {d.file_type === "xlsx" ? <FileSpreadsheet className="ic" aria-hidden="true" /> : <FileText className="ic" aria-hidden="true" />}
                        {d.filename}
                      </span>
                    </td>
                    <td className="folder">{d.folder}</td>
                    <td className="num hide-sm">{d.status === "indexing" ? "" : d.chunk_count}</td>
                    <td className="when hide-sm">{formatWhen(d.updated_at)}</td>
                    <td><Status d={d} /></td>
                    <td>
                      {admin && d.status !== "indexing" && (
                        <button
                          type="button"
                          className="btn ghost iconbtn"
                          aria-label={`Xoá ${d.filename}`}
                          onClick={() => { setNotice(null); setConfirmId(d.id); }}
                        >
                          <Trash2 className="ic" aria-hidden="true" />
                        </button>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
