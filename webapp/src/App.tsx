import { useEffect, useState } from "react";
import { haptic, tg } from "./api";
import Home from "./pages/Home";
import Finance from "./pages/Finance";
import Health from "./pages/Health";
import Sport from "./pages/Sport";
import Assistant from "./pages/Assistant";
import Reminders from "./pages/Reminders";
import Settings from "./pages/Settings";

export type Page = "home" | "finance" | "health" | "sport" | "ai" | "reminders" | "settings";

const NAV: [Page, string, string][] = [
  ["home", "🏠", "Главная"],
  ["finance", "💰", "Деньги"],
  ["health", "🍎", "Здоровье"],
  ["sport", "🏋️", "Спорт"],
  ["ai", "✨", "Claude"],
];

export default function App() {
  const [page, setPage] = useState<Page>(() => (location.hash.slice(1) as Page) || "home");

  const go = (p: Page) => {
    haptic();
    setPage(p);
    location.hash = p;
    window.scrollTo(0, 0);
  };

  // Кнопка «Назад» Telegram для вложенных экранов
  useEffect(() => {
    const back = tg?.BackButton;
    if (!back) return;
    const nested = page === "reminders" || page === "settings";
    const handler = () => go("home");
    if (nested) {
      back.show();
      back.onClick(handler);
    } else back.hide();
    return () => back.offClick?.(handler);
  }, [page]);

  return (
    <div className="app">
      <main>
        {page === "home" && <Home go={go} />}
        {page === "finance" && <Finance />}
        {page === "health" && <Health />}
        {page === "sport" && <Sport />}
        {page === "ai" && <Assistant />}
        {page === "reminders" && <Reminders />}
        {page === "settings" && <Settings />}
      </main>
      <nav className="bottom-nav">
        {NAV.map(([p, icon, label]) => (
          <button key={p} className={page === p ? "active" : ""} onClick={() => go(p)}>
            <span className="nav-icon">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
