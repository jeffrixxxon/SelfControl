import { useState } from "react";
import { api, confirmAction, fmtDate, haptic, nowLocal } from "../api";
import { Card, Empty, ErrorLine, Field, Progress, Sheet, Sparkline, Stat, Tabs, useLoad } from "../ui";

type Tab = "food" | "meds" | "weight";
const MEAL_TYPES: Record<string, string> = { breakfast: "Завтрак", lunch: "Обед", dinner: "Ужин", snack: "Перекус" };

export default function Health() {
  const [tab, setTab] = useState<Tab>("food");
  return (
    <div className="page">
      <h1>Здоровье</h1>
      <Tabs value={tab} onChange={setTab} items={[["food", "Питание"], ["meds", "Лекарства"], ["weight", "Вес"]]} />
      {tab === "food" && <Food />}
      {tab === "meds" && <Meds />}
      {tab === "weight" && <Weight />}
    </div>
  );
}

function Food() {
  const today = useLoad(() => api.get("/health/today"));
  const [open, setOpen] = useState(false);
  const empty = { description: "", meal_type: "lunch", calories: "", protein: "", fat: "", carbs: "" };
  const [form, setForm] = useState<any>(empty);
  const num = (v: string) => (v === "" ? null : Number(v));

  const save = async () => {
    await api.post("/meals", { ...form, calories: num(form.calories), protein: num(form.protein), fat: num(form.fat), carbs: num(form.carbs) });
    haptic("success"); setOpen(false); setForm(empty); today.reload();
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить запись?"))) return;
    await api.del(`/meals/${id}`); today.reload();
  };

  const d = today.data;
  return (
    <>
      {d && (
        <Card>
          <div className="stats">
            <Stat label="Ккал" value={d.totals.calories} sub={d.calorie_goal ? `из ${d.calorie_goal}` : undefined} />
            <Stat label="Белки" value={`${d.totals.protein} г`} />
            <Stat label="Жиры" value={`${d.totals.fat} г`} />
            <Stat label="Углев." value={`${d.totals.carbs} г`} />
          </div>
          {d.calorie_goal && <Progress value={d.totals.calories} max={d.calorie_goal} warn={90} />}
        </Card>
      )}
      <Card title="Сегодня" action={<button className="primary small" onClick={() => setOpen(true)}>+ Еда</button>}>
        {d?.meals.length ? d.meals.map((m: any) => (
          <div key={m.id} className="list-row" onClick={() => remove(m.id)}>
            <div>
              <div>{m.description}</div>
              <div className="muted small">{MEAL_TYPES[m.meal_type] || "Приём пищи"} · {fmtDate(m.eaten_at)}</div>
            </div>
            <b>{m.calories ? `${Math.round(m.calories)} ккал` : "—"}</b>
          </div>
        )) : <Empty>Пришли боту фото тарелки или напиши «на завтрак овсянка с бананом» — Claude посчитает КБЖУ.</Empty>}
      </Card>
      <Sheet open={open} title="Приём пищи" onClose={() => setOpen(false)}>
        <Field label="Что ели"><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Тип">
          <select value={form.meal_type} onChange={(e) => setForm({ ...form, meal_type: e.target.value })}>
            {Object.entries(MEAL_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <div className="grid4">
          {(["calories", "protein", "fat", "carbs"] as const).map((k) => (
            <Field key={k} label={{ calories: "Ккал", protein: "Б", fat: "Ж", carbs: "У" }[k]}>
              <input type="number" inputMode="decimal" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
        <button className="primary wide" disabled={!form.description} onClick={save}>Сохранить</button>
      </Sheet>
    </>
  );
}

function Meds() {
  const meds = useLoad(() => api.get("/medications"));
  const today = useLoad(() => api.get("/health/today"));
  const [edit, setEdit] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const takenMap: Record<number, any> = {};
  today.data?.medications.forEach((m: any) => (takenMap[m.id] = m));

  const save = async () => {
    try {
      const body = { ...edit, times: String(edit.timesStr || "").split(/[ ,;]+/).filter(Boolean),
        end_date: edit.end_date || null, start_date: edit.start_date || null };
      delete body.timesStr;
      if (edit.id) await api.put(`/medications/${edit.id}`, body);
      else await api.post("/medications", body);
      haptic("success"); setEdit(null); setErr(null); meds.reload(); today.reload();
    } catch (e: any) { setErr(e.message); }
  };
  const log = async (id: number, status: string) => {
    await api.post(`/medications/${id}/log`, { status });
    haptic("success"); today.reload();
  };
  const remove = async () => {
    if (!(await confirmAction("Удалить лекарство и его напоминания?"))) return;
    await api.del(`/medications/${edit.id}`); setEdit(null); meds.reload(); today.reload();
  };

  return (
    <>
      <Card title="Курс приёма" action={<button className="primary small" onClick={() => setEdit({ name: "", dosage: "", timesStr: "09:00", active: true })}>+ Лекарство</button>}>
        {meds.data?.length ? meds.data.map((m: any) => {
          const t = takenMap[m.id];
          return (
            <div key={m.id} className={`med ${m.active ? "" : "closed"}`}>
              <div className="between" onClick={() => setEdit({ ...m, timesStr: (m.times || []).join(", ") })}>
                <div>
                  <div>💊 <b>{m.name}</b> {m.dosage}</div>
                  <div className="muted small">{(m.times || []).join(" · ") || "без расписания"}{m.end_date && ` · до ${fmtDate(m.end_date, false)}`}</div>
                </div>
                {t && <span className={`chip ${t.planned && t.taken >= t.planned ? "done" : ""}`}>{t.taken}/{t.planned}</span>}
              </div>
              {m.active && (
                <div className="row-gap top-gap">
                  <button className="secondary grow" onClick={() => log(m.id, "taken")}>✅ Принял</button>
                  <button className="secondary" onClick={() => log(m.id, "skipped")}>⏭ Пропуск</button>
                </div>
              )}
            </div>
          );
        }) : <Empty>Добавь лекарства — бот напомнит в нужное время и спросит, принял ли ты.</Empty>}
      </Card>
      <p className="muted small center">Claude не назначает лечение. Дозировки — только по назначению врача.</p>

      <Sheet open={!!edit} title={edit?.id ? "Лекарство" : "Новое лекарство"} onClose={() => setEdit(null)}>
        {edit && (
          <>
            <Field label="Название"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Дозировка"><input value={edit.dosage || ""} placeholder="20 мг" onChange={(e) => setEdit({ ...edit, dosage: e.target.value })} /></Field>
            <Field label="Время приёма (через запятую)"><input value={edit.timesStr} placeholder="08:00, 20:00" onChange={(e) => setEdit({ ...edit, timesStr: e.target.value })} /></Field>
            <Field label="Принимать до"><input type="date" value={edit.end_date || ""} onChange={(e) => setEdit({ ...edit, end_date: e.target.value })} /></Field>
            <Field label="Заметки"><input value={edit.notes || ""} placeholder="после еды" onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
            <label className="check"><input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} /> Курс активен</label>
            <ErrorLine error={err} />
            <button className="primary wide" disabled={!edit.name} onClick={save}>Сохранить</button>
            {edit.id && <button className="danger wide top-gap" onClick={remove}>Удалить</button>}
          </>
        )}
      </Sheet>
    </>
  );
}

function Weight() {
  const list = useLoad(() => api.get("/weights"));
  const me = useLoad(() => api.get("/me"));
  const [value, setValue] = useState("");
  const [when, setWhen] = useState(nowLocal());

  const save = async () => {
    await api.post("/weights", { weight_kg: Number(value.replace(",", ".")), measured_at: when.replace("T", " ") });
    haptic("success"); setValue(""); list.reload();
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить замер?"))) return;
    await api.del(`/weights/${id}`); list.reload();
  };

  const ws = list.data || [];
  const last = ws.at(-1), first = ws[0];
  const bmi = last && me.data?.height_cm ? last.weight_kg / (me.data.height_cm / 100) ** 2 : null;

  return (
    <>
      <Card>
        <div className="stats">
          <Stat label="Сейчас" value={last ? `${last.weight_kg} кг` : "—"} />
          <Stat label="Изменение" value={last && first ? `${(last.weight_kg - first.weight_kg).toFixed(1)} кг` : "—"} />
          <Stat label={bmi ? "ИМТ" : "Цель"} value={bmi ? bmi.toFixed(1) : me.data?.weight_goal ? `${me.data.weight_goal} кг` : "—"} />
        </div>
        <Sparkline values={ws.map((w: any) => w.weight_kg)} />
      </Card>
      <Card title="Новый замер">
        <div className="row-gap">
          <input type="number" inputMode="decimal" placeholder="кг" value={value} onChange={(e) => setValue(e.target.value)} />
          <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </div>
        <button className="primary wide top-gap" disabled={!value} onClick={save}>Записать</button>
      </Card>
      <Card title="История">
        <ErrorLine error={list.error} />
        {ws.length ? [...ws].reverse().map((w: any) => (
          <div key={w.id} className="list-row" onClick={() => remove(w.id)}>
            <span>{fmtDate(w.measured_at)}</span><b>{w.weight_kg} кг</b>
          </div>
        )) : <Empty>Замеров пока нет</Empty>}
      </Card>
    </>
  );
}
