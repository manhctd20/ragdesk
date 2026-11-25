import { Folder, MessageSquare, Moon, Plus, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Link, NavLink } from "react-router";
import { THEME_KEY, groupByDay, type Conversation } from "./history";

function currentTheme(): "light" | "dark" {
  const t = document.documentElement.dataset.theme;
  if (t === "light" || t === "dark") return t;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const themeListeners = new Set<() => void>();

function subscribeTheme(notify: () => void) {
  themeListeners.add(notify);
  return () => void themeListeners.delete(notify);
}

export default function Sidebar({ conversations }: { conversations: Conversation[] }) {
  const theme = useSyncExternalStore(subscribeTheme, currentTheme);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    themeListeners.forEach((n) => n());
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // storage unavailable: theme applies for this tab only
    }
  }

  return (
    <div className="side-in">
      <div className="brand">Tra cứu nội bộ</div>
      <Link className="nav" to="/">
        <Plus className="ic" aria-hidden="true" />
        Cuộc hỏi mới
      </Link>
      <div className="hist">
        {groupByDay(conversations).map((g) => (
          <section key={g.label}>
            <div className="group">{g.label}</div>
            {g.items.map((c) => (
              <NavLink key={c.id} className="nav" to={`/c/${c.id}`}>
                <MessageSquare className="ic" aria-hidden="true" />
                <span className="ellipsis">{c.title}</span>
              </NavLink>
            ))}
          </section>
        ))}
      </div>
      <div className="side-foot">
        <NavLink className="nav" to="/tai-lieu">
          <Folder className="ic" aria-hidden="true" />
          Tài liệu
        </NavLink>
        <button
          type="button"
          className="btn ghost iconbtn"
          onClick={toggle}
          aria-label={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
        >
          {theme === "dark" ? <Sun className="ic" aria-hidden="true" /> : <Moon className="ic" aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}
