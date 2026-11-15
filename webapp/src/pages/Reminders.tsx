import { useState } from "react";
import { api, confirmAction, fmtDate, haptic } from "../api";
import { Card, Empty, ErrorLine, Field, Sheet, Tabs, useLoad } from "../ui";

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const KINDS: Record<string, string> = { custom: "⏰ Обычное", workout: "🏋️ Тренировка", motivation: "🔥 Мотивация от Claude", medication: "💊 Лекарство" };

export default function Reminders() {
  const list = useLoad(() => api.get("/reminders"));
  const [edit, setEdit] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    try {
      const body = {
        text: edit.text, kind: edit.kind, active: edit.active,
        time_of_day: edit.mode === "repeat" ? edit.time_of_day : null,
        days_of_week: edit.mode === "repeat" ? edit.days_of_week : [],
        run_at: edit.mode === "once" ? edit.run_at.replace("T", " ") : null,
      };
      if (edit.id) await api.put(`/reminders/${edit.id}`, body);
      else await api.post("/reminders", body);
      haptic("success"); setEdit(null); setErr(null); list.reload();
    } catch (e: any) { setErr(e.message); }
  };
  const remove = async () => {
    if (!(await confirmAction("Удалить напоминание?"))) return;
    await api.del(`/reminders/${edit.id}`); setEdit(null); list.reload();
  };
  const toggleDay = (d: number) => {
    const s = new Set<number>(edit.days_of_week);
    s.has(d) ? s.delete(d) : s.add(d);
    setEdit({ ...edit, days_of_week: [...s].sort() });
  };
  const openEdit = (r: any) => setEdit({
    ...r, mode: r.time_of_day ? "repeat" : "once",
    run_at: r.run_at ? new Date(r.run_at).toLocaleString("sv-SE").slice(0, 16).replace(" ", "T") : "",
  });

  const describe = (r: any) => r.time_of_day
    ? `${r.time_of_day} · ${r.days_of_week?.length ? r.days_of_week.map((d: number) => DAYS[d]).join(", ") : "каждый день"}`
    : r.run_at ? fmtDate(r.run_at) : "";

  return (
    <div className="page">
      <h1>Напоминания</h1>
      <Card action={<button className="primary small" onClick={() => setEdit({ text: "", kind: "custom", mode: "repeat", time_of_day: "09:00", days_of_week: [], run_at: "", active: true })}>+ Напоминание</button>}
        title="Все">
        <ErrorLine error={list.error} />
        {list.data?.length ? list.data.map((r: any) => (
          <div key={r.id} className={`list-row ${r.active ? "" : "closed"}`} onClick={() => r.kind !== "medication" && openEdit(r)}>
            <div>
              <div>{KINDS[r.kind]?.split(" ")[0]} {r.text}</div>
              <div className="muted small">{describe(r)}{r.kind === "medication" && " · меняется в разделе «Лекарства»"}</div>
            </div>
            {r.next_run_at && <span className="muted small">{fmtDate(r.next_run_at)}</span>}
          </div>
        )) : <Empty>Скажи боту: «напоминай пить воду каждые будни в 11:00».</Empty>}
      </Card>

      <Sheet open={!!edit} title={edit?.id ? "Напоминание" : "Новое напоминание"} onClose={() => setEdit(null)}>
        {edit && (
          <>
            <Field label="Текст"><input value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} /></Field>
            <Field label="Тип"><select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>
              {Object.entries(KINDS).filter(([k]) => k !== "medication").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></Field>
            <Tabs value={edit.mode} onChange={(m) => setEdit({ ...edit, mode: m })} items={[["repeat", "Повторять"], ["once", "Один раз"]]} />
            {edit.mode === "repeat" ? (
              <>
                <Field label="Время"><input type="time" value={edit.time_of_day || ""} onChange={(e) => setEdit({ ...edit, time_of_day: e.target.value })} /></Field>
                <div className="days">
                  {DAYS.map((d, i) => (
                    <button key={d} className={edit.days_of_week.includes(i) ? "active" : ""} onClick={() => toggleDay(i)}>{d}</button>
                  ))}
                </div>
                <div className="muted small">Не выбрано ни одного дня — каждый день</div>
              </>
            ) : (
              <Field label="Когда"><input type="datetime-local" value={edit.run_at} onChange={(e) => setEdit({ ...edit, run_at: e.target.value })} /></Field>
            )}
            <label className="check"><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} /> Включено</label>
            <ErrorLine error={err} />
            <button className="primary wide" disabled={!edit.text} onClick={save}>Сохранить</button>
            {edit.id && <button className="danger wide top-gap" onClick={remove}>Удалить</button>}
          </>
        )}
      </Sheet>
    </div>
  );
}
