import { useState } from "react";
import { api, confirmAction, fmtDate, haptic, nowLocal } from "../api";
import { Card, GoalProgress, Empty, Field, Progress, Sheet, Stat, Tabs, useLoad } from "../ui";

const TYPES = ["Силовая", "Бег", "Ходьба", "Велосипед", "Плавание", "Йога", "Растяжка", "Другое"];
const AREAS: Record<string, string> = { finance: "💰 Финансы", health: "🍎 Здоровье", fitness: "🏋️ Спорт", other: "✨ Другое" };

export default function Sport() {
  const [tab, setTab] = useState<"workouts" | "goals">("workouts");
  return (
    <div className="page">
      <h1>Спорт и цели</h1>
      <Tabs value={tab} onChange={setTab} items={[["workouts", "Тренировки"], ["goals", "Цели"]]} />
      {tab === "workouts" ? <Workouts /> : <Goals />}
    </div>
  );
}

type Ex = { name: string; sets?: number; reps?: number; weight?: number; distance_km?: number };

function Workouts() {
  const week = useLoad(() => api.get("/fitness/week"));
  const list = useLoad(() => api.get("/workouts"));
  const [open, setOpen] = useState(false);
  const empty = { type: "Силовая", duration_min: "", calories: "", notes: "", performed_at: nowLocal() };
  const [form, setForm] = useState<any>(empty);
  const [ex, setEx] = useState<Ex[]>([]);

  const save = async () => {
    await api.post("/workouts", {
      ...form, duration_min: form.duration_min ? Number(form.duration_min) : null,
      calories: form.calories ? Number(form.calories) : null,
      performed_at: form.performed_at.replace("T", " "), exercises: ex.filter((e) => e.name),
    });
    haptic("success"); setOpen(false); setForm(empty); setEx([]); week.reload(); list.reload();
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить тренировку?"))) return;
    await api.del(`/workouts/${id}`); week.reload(); list.reload();
  };
  const setExField = (i: number, k: keyof Ex, v: string) =>
    setEx(ex.map((e, j) => (j === i ? { ...e, [k]: k === "name" ? v : v === "" ? undefined : Number(v) } : e)));

  return (
    <>
      {week.data && (
        <Card title="Эта неделя">
          <div className="stats">
            <Stat label="Тренировок" value={week.data.count} />
            <Stat label="Минут" value={week.data.minutes} />
            <Stat label="Ккал" value={week.data.calories} />
          </div>
        </Card>
      )}
      <Card title="История" action={<button className="primary small" onClick={() => setOpen(true)}>+ Тренировка</button>}>
        {list.data?.length ? list.data.map((w: any) => (
          <div key={w.id} className="list-row" onClick={() => remove(w.id)}>
            <div>
              <div><b>{w.type}</b>{w.duration_min && ` · ${w.duration_min} мин`}</div>
              <div className="muted small">
                {fmtDate(w.performed_at)}
                {w.exercises?.length > 0 && " · " + w.exercises.map((e: Ex) =>
                  `${e.name}${e.sets ? ` ${e.sets}×${e.reps ?? ""}` : ""}${e.weight ? ` ${e.weight}кг` : ""}${e.distance_km ? ` ${e.distance_km}км` : ""}`).join(", ")}
              </div>
            </div>
            {w.calories && <span className="muted small">{Math.round(w.calories)} ккал</span>}
          </div>
        )) : <Empty>Скажи боту голосом «сделал жим 3 по 10 с 60 кг и подтягивания» — он всё запишет.</Empty>}
      </Card>

      <Sheet open={open} title="Тренировка" onClose={() => setOpen(false)}>
        <Field label="Тип"><select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
          {TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <div className="grid2">
          <Field label="Минут"><input type="number" value={form.duration_min} onChange={(e) => setForm({ ...form, duration_min: e.target.value })} /></Field>
          <Field label="Ккал"><input type="number" value={form.calories} onChange={(e) => setForm({ ...form, calories: e.target.value })} /></Field>
        </div>
        <div className="muted small">Упражнения</div>
        {ex.map((e, i) => (
          <div key={i} className="ex-row">
            <input placeholder="Упражнение" value={e.name} onChange={(v) => setExField(i, "name", v.target.value)} />
            <input placeholder="подх" type="number" value={e.sets ?? ""} onChange={(v) => setExField(i, "sets", v.target.value)} />
            <input placeholder="повт" type="number" value={e.reps ?? ""} onChange={(v) => setExField(i, "reps", v.target.value)} />
            <input placeholder="кг" type="number" value={e.weight ?? ""} onChange={(v) => setExField(i, "weight", v.target.value)} />
          </div>
        ))}
        <button className="secondary wide" onClick={() => setEx([...ex, { name: "" }])}>+ Упражнение</button>
        <Field label="Заметки"><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
        <Field label="Когда"><input type="datetime-local" value={form.performed_at} onChange={(e) => setForm({ ...form, performed_at: e.target.value })} /></Field>
        <button className="primary wide" onClick={save}>Сохранить</button>
      </Sheet>
    </>
  );
}

function Goals() {
  const list = useLoad(() => api.get("/goals"));
  const [edit, setEdit] = useState<any>(null);
  const num = (v: any) => (v === "" || v == null ? null : Number(v));

  const save = async () => {
    const body = { ...edit, target_value: num(edit.target_value), current_value: num(edit.current_value), deadline: edit.deadline || null };
    if (edit.id) await api.put(`/goals/${edit.id}`, body);
    else await api.post("/goals", body);
    haptic("success"); setEdit(null); list.reload();
  };
  const remove = async () => {
    if (!(await confirmAction("Удалить цель?"))) return;
    await api.del(`/goals/${edit.id}`); setEdit(null); list.reload();
  };

  return (
    <Card title="Мои цели" action={<button className="primary small" onClick={() => setEdit({ title: "", area: "fitness", done: false })}>+ Цель</button>}>
      {list.data?.length ? list.data.map((g: any) => (
        <div key={g.id} className={`goal ${g.done ? "closed" : ""}`} onClick={() => setEdit(g)}>
          <div className="between">
            <span>{g.done ? "✅" : AREAS[g.area]?.split(" ")[0]} {g.title}</span>
            {g.deadline && <span className="muted small">до {fmtDate(g.deadline, false)}</span>}
          </div>
          {g.target_value != null && (
            <>
              <GoalProgress current={g.current_value} target={g.target_value} />
              <div className="muted small">{g.current_value ?? 0} / {g.target_value} {g.unit}</div>
            </>
          )}
        </div>
      )) : <Empty>Поставь цель — Claude будет учитывать её в советах и мотивации.</Empty>}

      <Sheet open={!!edit} title={edit?.id ? "Цель" : "Новая цель"} onClose={() => setEdit(null)}>
        {edit && (
          <>
            <Field label="Цель"><input value={edit.title} placeholder="Пробежать 10 км" onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
            <Field label="Сфера"><select value={edit.area} onChange={(e) => setEdit({ ...edit, area: e.target.value })}>
              {Object.entries(AREAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <div className="grid3">
              <Field label="Сейчас"><input type="number" value={edit.current_value ?? ""} onChange={(e) => setEdit({ ...edit, current_value: e.target.value })} /></Field>
              <Field label="Цель"><input type="number" value={edit.target_value ?? ""} onChange={(e) => setEdit({ ...edit, target_value: e.target.value })} /></Field>
              <Field label="Ед."><input value={edit.unit ?? ""} placeholder="км" onChange={(e) => setEdit({ ...edit, unit: e.target.value })} /></Field>
            </div>
            <Field label="Срок"><input type="date" value={edit.deadline ?? ""} onChange={(e) => setEdit({ ...edit, deadline: e.target.value })} /></Field>
            <label className="check"><input type="checkbox" checked={edit.done} onChange={(e) => setEdit({ ...edit, done: e.target.checked })} /> Выполнена</label>
            <button className="primary wide" disabled={!edit.title} onClick={save}>Сохранить</button>
            {edit.id && <button className="danger wide top-gap" onClick={remove}>Удалить</button>}
          </>
        )}
      </Sheet>
    </Card>
  );
}
