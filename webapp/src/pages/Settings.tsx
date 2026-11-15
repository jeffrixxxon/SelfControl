import { useEffect, useState } from "react";
import { api, haptic } from "../api";
import { Card, ErrorLine, Field, useLoad } from "../ui";

const TIMEZONES = ["Europe/Kaliningrad", "Europe/Moscow", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Omsk",
  "Asia/Novosibirsk", "Asia/Krasnoyarsk", "Asia/Irkutsk", "Asia/Yakutsk", "Asia/Vladivostok", "Asia/Magadan",
  "Asia/Kamchatka", "Europe/Minsk", "Europe/Kyiv", "Asia/Almaty", "Asia/Tashkent", "Asia/Tbilisi", "Asia/Yerevan",
  "Europe/Istanbul", "Asia/Dubai", "Europe/Berlin", "Europe/London", "UTC"];
const CURRENCIES = ["RUB", "USD", "EUR", "KZT", "BYN", "UAH", "UZS", "GEL", "AMD", "TRY", "AED"];

export default function Settings() {
  const me = useLoad(() => api.get("/me"));
  const [form, setForm] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { if (me.data) setForm(me.data); }, [me.data]);
  if (!form) return <div className="page"><ErrorLine error={me.error} /></div>;

  const num = (v: any) => (v === "" || v == null ? null : Number(v));
  const save = async () => {
    try {
      await api.put("/me", {
        timezone: form.timezone, currency: form.currency, calorie_goal: num(form.calorie_goal),
        weight_goal: num(form.weight_goal), height_cm: num(form.height_cm),
        daily_report_enabled: form.daily_report_enabled, daily_report_time: form.daily_report_time, about: form.about,
      });
      haptic("success"); setSaved(true); setErr(null); setTimeout(() => setSaved(false), 2000);
    } catch (e: any) { setErr(e.message); }
  };
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="page">
      <h1>Настройки</h1>
      <Card title="Основное">
        <Field label="Часовой пояс"><select value={form.timezone} onChange={set("timezone")}>
          {[...new Set([form.timezone, ...TIMEZONES])].map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Валюта"><select value={form.currency} onChange={set("currency")}>
          {[...new Set([form.currency, ...CURRENCIES])].map((c) => <option key={c}>{c}</option>)}</select></Field>
      </Card>
      <Card title="Здоровье">
        <div className="grid3">
          <Field label="Ккал/день"><input type="number" value={form.calorie_goal ?? ""} onChange={set("calorie_goal")} /></Field>
          <Field label="Цель, кг"><input type="number" value={form.weight_goal ?? ""} onChange={set("weight_goal")} /></Field>
          <Field label="Рост, см"><input type="number" value={form.height_cm ?? ""} onChange={set("height_cm")} /></Field>
        </div>
      </Card>
      <Card title="Claude">
        <label className="check"><input type="checkbox" checked={form.daily_report_enabled} onChange={set("daily_report_enabled")} /> Вечерний разбор дня</label>
        <Field label="Время разбора"><input type="time" value={form.daily_report_time} onChange={set("daily_report_time")} /></Field>
        <Field label="О себе (Claude учитывает в советах)">
          <textarea rows={5} value={form.about ?? ""} placeholder="Цели, ограничения по здоровью, режим дня, что мотивирует…" onChange={set("about")} />
        </Field>
      </Card>
      <ErrorLine error={err} />
      <button className="primary wide" onClick={save}>{saved ? "Сохранено ✓" : "Сохранить"}</button>
    </div>
  );
}
