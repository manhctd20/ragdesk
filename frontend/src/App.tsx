import { Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Route, Routes, useLocation, useParams } from "react-router";
import Chat from "./Chat";
import TaiLieu from "./TaiLieu";
import { loadHistory, saveHistory, upsertConversation, type Conversation } from "./history";
import Sidebar from "./Sidebar";

function ChatPage(props: { conversations: Conversation[]; onSave: (c: Conversation) => void }) {
  return <Chat key={useParams().id ?? "new"} {...props} />;
}

export default function App() {
  const [conversations, setConversations] = useState(loadHistory);
  const save = (c: Conversation) =>
    setConversations((list) => {
      const next = upsertConversation(list, c);
      saveHistory(next);
      return next;
    });
  const drawer = useRef<HTMLDialogElement>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    drawer.current?.close?.();
  }, [pathname]);

  return (
    <div className="app">
      <aside className="side">
        <Sidebar conversations={conversations} />
      </aside>
      <div className="col">
        <header className="topbar">
          <button type="button" className="btn ghost iconbtn" aria-label="Mở menu" onClick={() => drawer.current?.showModal()}>
            <Menu className="ic" aria-hidden="true" />
          </button>
          <span className="brand">Tra cứu nội bộ</span>
        </header>
        <main className="main">
          <Routes>
            <Route path="/" element={<ChatPage conversations={conversations} onSave={save} />} />
            <Route path="/c/:id" element={<ChatPage conversations={conversations} onSave={save} />} />
            <Route path="/tai-lieu" element={<TaiLieu />} />
          </Routes>
        </main>
      </div>
      <dialog ref={drawer} className="drawer" aria-label="Menu">
        <Sidebar conversations={conversations} />
      </dialog>
    </div>
  );
}
