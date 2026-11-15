// Клиент API: каждый запрос подписан initData из Telegram
declare global {
  interface Window {
    Telegram?: { WebApp: any };
  }
}

export const tg = window.Telegram?.WebApp;

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-Telegram-Init-Data": tg?.initData || "" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (!res.ok) {
    let msg = `Ошибка ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  get: <T = any>(p: string) => request<T>("GET", p),
  post: <T = any>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T = any>(p: string, b: unknown) => request<T>("PUT", p, b),
  del: <T = any>(p: string) => request<T>("DELETE", p),
};

export function haptic(type: "light" | "success" | "error" = "light") {
  try {
    if (type === "light") tg?.HapticFeedback?.impactOccurred("light");
    else tg?.HapticFeedback?.notificationOccurred(type);
  } catch {}
}

export function confirmAction(text: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (tg?.showConfirm) tg.showConfirm(text, (ok: boolean) => resolve(ok));
    else resolve(window.confirm(text));
  });
}

export const money = (v: number, cur = "RUB") =>
  new Intl.NumberFormat("ru-RU", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(v || 0);

export const fmtDate = (iso: string, withTime = true) =>
  new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });

// Локальное время для полей datetime-local → строка 'YYYY-MM-DD HH:MM'
export const nowLocal = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};
