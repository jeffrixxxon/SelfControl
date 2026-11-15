import { useState } from "react";
import { api, confirmAction, fmtDate, haptic, money, nowLocal } from "../api";
import { Card, Empty, ErrorLine, Field, Progress, Sheet, Stat, Tabs, useLoad } from "../ui";

type Tab = "ops" | "budgets" | "debts";

export default function Finance() {
  const [tab, setTab] = useState<Tab>("ops");
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const me = useLoad(() => api.get("/me"));
  const cur = me.data?.currency || "RUB";

  const shift = (d: number) => {
    const dt = new Date(ym.y, ym.m - 1 + d, 1);
    setYm({ y: dt.getFullYear(), m: dt.getMonth() + 1 });
  };
  const mn = new Date(ym.y, ym.m - 1, 1).toLocaleString("ru-RU", { month: "long" });
  const monthName = `${mn[0].toUpperCase()}${mn.slice(1)} ${ym.y}`;

  return (
    <div className="page">
      <h1>Деньги</h1>
      <Tabs value={tab} onChange={setTab} items={[["ops", "Операции"], ["budgets", "Бюджеты"], ["debts", "Долги"]]} />
      {tab !== "debts" && (
        <div className="month-switch">
          <button className="icon" onClick={() => shift(-1)}>‹</button>
          <span>{monthName}</span>
          <button className="icon" onClick={() => shift(1)}>›</button>
        </div>
      )}
      {tab === "ops" && <Operations ym={ym} cur={cur} />}
      {tab === "budgets" && <Budgets ym={ym} cur={cur} />}
      {tab === "debts" && <Debts cur={cur} />}
    </div>
  );
}

function Operations({ ym, cur }: { ym: { y: number; m: number }; cur: string }) {
  const q = `?year=${ym.y}&month=${ym.m}`;
  const list = useLoad(() => api.get(`/transactions${q}`), [q]);
  const sum = useLoad(() => api.get(`/finance/summary${q}`), [q]);
  const cats = useLoad(() => api.get("/categories"));
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<any>({ kind: "expense", amount: "", category: "Продукты", description: "", occurred_at: nowLocal() });
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    try {
      await api.post("/transactions", { ...form, amount: Number(form.amount), occurred_at: form.occurred_at.replace("T", " ") });
      haptic("success");
      setOpen(false);
      setForm({ ...form, amount: "", description: "" });
      list.reload(); sum.reload();
    } catch (e: any) { setErr(e.message); haptic("error"); }
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить операцию?"))) return;
    await api.del(`/transactions/${id}`);
    list.reload(); sum.reload();
  };

  const s = sum.data;
  const maxCat = s ? Math.max(1, ...Object.values<number>(s.by_category)) : 1;
  const catList: string[] = cats.data ? cats.data[form.kind] : [];

  return (
    <>
      {s && (
        <Card>
          <div className="stats">
            <Stat label="Расходы" value={money(s.spent, cur)} />
            <Stat label="Доходы" value={money(s.income, cur)} />
            <Stat label="Баланс" value={money(s.income - s.spent, cur)} />
          </div>
          {Object.entries<number>(s.by_category).map(([c, v]) => (
            <div key={c} className="cat-row">
              <div className="between small"><span>{c}</span><span>{money(v, cur)}</span></div>
              <div className="progress thin"><div className="bar neutral" style={{ width: `${(v / maxCat) * 100}%` }} /></div>
            </div>
          ))}
        </Card>
      )}
      <Card title="Операции" action={<button className="primary small" onClick={() => setOpen(true)}>+ Добавить</button>}>
        <ErrorLine error={list.error} />
        {list.data?.length ? list.data.map((t: any) => (
          <div key={t.id} className="list-row" onClick={() => remove(t.id)}>
            <div>
              <div>{t.description || t.category} {t.source === "receipt" && "🧾"}{t.source === "voice" && "🎙"}</div>
              <div className="muted small">{t.category} · {fmtDate(t.occurred_at)}</div>
            </div>
            <b className={t.kind === "income" ? "pos" : ""}>{t.kind === "income" ? "+" : "−"}{money(t.amount, t.currency)}</b>
          </div>
        )) : <Empty>Пока пусто. Напиши боту «кофе 250» или пришли фото чека.</Empty>}
      </Card>

      <Sheet open={open} title="Новая операция" onClose={() => setOpen(false)}>
        <Tabs value={form.kind} onChange={(k) => setForm({ ...form, kind: k, category: k === "income" ? "Зарплата" : "Продукты" })}
          items={[["expense", "Расход"], ["income", "Доход"]]} />
        <Field label="Сумма"><input type="number" inputMode="decimal" value={form.amount} autoFocus
          onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label="Категория">
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {catList.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Описание"><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Когда"><input type="datetime-local" value={form.occurred_at} onChange={(e) => setForm({ ...form, occurred_at: e.target.value })} /></Field>
        <ErrorLine error={err} />
        <button className="primary wide" disabled={!form.amount} onClick={save}>Сохранить</button>
      </Sheet>
    </>
  );
}

function Budgets({ ym, cur }: { ym: { y: number; m: number }; cur: string }) {
  const q = `?year=${ym.y}&month=${ym.m}`;
  const sum = useLoad(() => api.get(`/finance/summary${q}`), [q]);
  const cats = useLoad(() => api.get("/categories"));
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ category: "", monthly_limit: "" });

  const save = async () => {
    await api.post("/budgets", { category: form.category || null, monthly_limit: Number(form.monthly_limit) });
    haptic("success"); setOpen(false); sum.reload();
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить бюджет?"))) return;
    await api.del(`/budgets/${id}`); sum.reload();
  };

  return (
    <Card title="Лимиты на месяц" action={<button className="primary small" onClick={() => setOpen(true)}>+ Лимит</button>}>
      {sum.data?.budgets.length ? sum.data.budgets.map((b: any) => (
        <div key={b.id} className="goal" onClick={() => remove(b.id)}>
          <div className="between"><span>{b.category}</span>
            <span className={`small ${b.left < 0 ? "neg" : "muted"}`}>{money(b.spent, cur)} / {money(b.limit, cur)}</span></div>
          <Progress value={b.spent} max={b.limit} />
        </div>
      )) : <Empty>Задай общий лимит или лимиты по категориям — Claude будет предупреждать о перерасходе.</Empty>}
      <Sheet open={open} title="Лимит" onClose={() => setOpen(false)}>
        <Field label="Категория">
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Весь бюджет</option>
            {cats.data?.expense.map((c: string) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Лимит в месяц"><input type="number" inputMode="decimal" value={form.monthly_limit}
          onChange={(e) => setForm({ ...form, monthly_limit: e.target.value })} /></Field>
        <button className="primary wide" disabled={!form.monthly_limit} onClick={save}>Сохранить</button>
      </Sheet>
    </Card>
  );
}

function Debts({ cur }: { cur: string }) {
  const list = useLoad(() => api.get("/debts?include_closed=true"));
  const [open, setOpen] = useState(false);
  const [pay, setPay] = useState<any>(null);
  const [amount, setAmount] = useState("");
  const [form, setForm] = useState({ direction: "i_owe", counterparty: "", amount: "", due_date: "", note: "" });

  const save = async () => {
    await api.post("/debts", { ...form, amount: Number(form.amount), due_date: form.due_date || null });
    haptic("success"); setOpen(false); list.reload();
  };
  const savePay = async () => {
    await api.post(`/debts/${pay.id}/payments`, { amount: Number(amount) });
    haptic("success"); setPay(null); setAmount(""); list.reload();
  };
  const remove = async (id: number) => {
    if (!(await confirmAction("Удалить долг вместе с историей?"))) return;
    await api.del(`/debts/${id}`); setPay(null); list.reload();
  };

  const debts = list.data || [];
  const sumOf = (dir: string) => debts.filter((d: any) => d.direction === dir && !d.closed).reduce((a: number, d: any) => a + d.remaining, 0);

  return (
    <>
      <Card>
        <div className="stats">
          <Stat label="Я должен" value={money(sumOf("i_owe"), cur)} />
          <Stat label="Мне должны" value={money(sumOf("owed_to_me"), cur)} />
        </div>
      </Card>
      <Card title="Долги" action={<button className="primary small" onClick={() => setOpen(true)}>+ Долг</button>}>
        {debts.length ? debts.map((d: any) => (
          <div key={d.id} className={`list-row ${d.closed ? "closed" : ""}`} onClick={() => setPay(d)}>
            <div>
              <div>{d.direction === "i_owe" ? "➡️" : "⬅️"} {d.counterparty}</div>
              <div className="muted small">
                {d.closed ? "закрыт" : `из ${money(d.amount, d.currency)}`}{d.due_date && ` · до ${fmtDate(d.due_date, false)}`}{d.note && ` · ${d.note}`}
              </div>
            </div>
            <b className={d.direction === "owed_to_me" ? "pos" : "neg"}>{money(d.remaining, d.currency)}</b>
          </div>
        )) : <Empty>Долгов нет 🎉</Empty>}
      </Card>

      <Sheet open={open} title="Новый долг" onClose={() => setOpen(false)}>
        <Tabs value={form.direction} onChange={(v) => setForm({ ...form, direction: v })}
          items={[["i_owe", "Я должен"], ["owed_to_me", "Мне должны"]]} />
        <Field label="Кто"><input value={form.counterparty} onChange={(e) => setForm({ ...form, counterparty: e.target.value })} /></Field>
        <Field label="Сумма"><input type="number" inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label="Вернуть до"><input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
        <Field label="Заметка"><input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
        <button className="primary wide" disabled={!form.counterparty || !form.amount} onClick={save}>Сохранить</button>
      </Sheet>

      <Sheet open={!!pay} title={pay ? `${pay.counterparty}: ${money(pay.remaining, cur)}` : ""} onClose={() => setPay(null)}>
        {pay && !pay.closed && (
          <>
            <Field label="Сумма погашения"><input type="number" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <div className="row-gap">
              <button className="secondary" onClick={() => setAmount(String(pay.remaining))}>Всю сумму</button>
              <button className="primary grow" disabled={!amount} onClick={savePay}>Погасить</button>
            </div>
          </>
        )}
        {pay?.payments.length > 0 && <div className="top-gap muted small">История:</div>}
        {pay?.payments.map((p: any) => (
          <div key={p.id} className="list-row small"><span>{fmtDate(p.paid_at)}</span><span>{money(p.amount, cur)}</span></div>
        ))}
        <button className="danger wide top-gap" onClick={() => pay && remove(pay.id)}>Удалить долг</button>
      </Sheet>
    </>
  );
}
