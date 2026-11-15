import { ReactNode, useCallback, useEffect, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    fn().then(setData).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { data, error, reload };
}

export function Card({ title, action, children }: { title?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || action) && (
        <div className="card-head">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Progress({ value, max, warn = 80 }: { value: number; max: number; warn?: number }) {
  const pct = max ? Math.min((value / max) * 100, 100) : 0;
  const raw = max ? (value / max) * 100 : 0;
  const cls = raw >= 100 ? "bad" : raw >= warn ? "warn" : "good";
  return (
    <div className="progress">
      <div className={`bar ${cls}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: [T, string][];
}) {
  return (
    <div className="tabs">
      {items.map(([k, label]) => (
        <button key={k} className={k === value ? "active" : ""} onClick={() => onChange(k)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Sheet({ open, title, onClose, children }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <h3>{title}</h3>
          <button className="icon" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Sparkline({ values, height = 60 }: { values: number[]; height?: number }) {
  if (values.length < 2) return <Empty>Нужно минимум 2 замера</Empty>;
  const w = 300;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${height - 6 - ((v - min) / span) * (height - 12)}`);
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="spark" preserveAspectRatio="none">
      <polyline points={pts.join(" ")} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinejoin="round" />
      {pts.length > 0 && <circle cx={pts[pts.length - 1].split(",")[0]} cy={pts[pts.length - 1].split(",")[1]} r="4" fill="var(--accent)" />}
    </svg>
  );
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <div className="error">{error}</div> : null;
}

// Прогресс цели: если цель меньше текущего значения (похудеть, сократить) — считаем в обратную сторону
export function GoalProgress({ current, target }: { current: number | null; target: number }) {
  const cur = current ?? 0;
  const value = target < cur ? target : cur;
  const max = target < cur ? cur : target;
  return <Progress value={value} max={max} warn={101} />;
}
