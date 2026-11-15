import { api, fmtDate, money } from "../api";
import type { Page } from "../App";
import { Card, GoalProgress, Empty, ErrorLine, Progress, Stat, useLoad } from "../ui";

export default function Home({ go }: { go: (p: Page) => void }) {
  const { data, error } = useLoad(() => api.get("/dashboard"));
  if (!data) return <div className="page"><ErrorLine error={error} />{!error && <div className="loader" />}</div>;

  const cur = data.user.currency;
  const f = data.finance, h = data.health, fit = data.fitness;
  const total = f.month.budgets.find((b: any) => b.category === "Всего");
  const lastW = h.weights.at(-1);
  const hour = new Date().getHours();
  const hello = hour < 6 ? "Доброй ночи" : hour < 12 ? "Доброе утро" : hour < 18 ? "Добрый день" : "Добрый вечер";

  return (
    <div className="page">
      <header className="hero">
        <div>
          <div className="muted">{hello},</div>
          <h1>{data.user.first_name || "друг"}</h1>
        </div>
        <div className="row-gap">
          <button className="icon big" onClick={() => go("reminders")}>⏰</button>
          <button className="icon big" onClick={() => go("settings")}>⚙️</button>
        </div>
      </header>

      <Card title="💰 Деньги" action={<button className="link" onClick={() => go("finance")}>Подробнее</button>}>
        <div className="stats">
          <Stat label="Сегодня" value={money(f.spent_today, cur)} />
          <Stat label="За месяц" value={money(f.month.spent, cur)} sub={`доход ${money(f.month.income, cur)}`} />
        </div>
        {total && (
          <>
            <div className="between small"><span>Бюджет месяца</span><span>{money(total.left, cur)} осталось</span></div>
            <Progress value={total.spent} max={total.limit} />
          </>
        )}
        {(f.i_owe > 0 || f.owed_to_me > 0) && (
          <div className="between small top-gap">
            <span>Я должен: <b>{money(f.i_owe, cur)}</b></span>
            <span>Мне должны: <b>{money(f.owed_to_me, cur)}</b></span>
          </div>
        )}
      </Card>

      <Card title="🍎 Здоровье" action={<button className="link" onClick={() => go("health")}>Подробнее</button>}>
        <div className="stats">
          <Stat label="Калории" value={`${h.totals.calories}`} sub={h.calorie_goal ? `из ${h.calorie_goal}` : "ккал"} />
          <Stat label="Вес" value={lastW ? `${lastW.weight_kg} кг` : "—"} sub={h.weight_goal ? `цель ${h.weight_goal}` : undefined} />
        </div>
        {h.calorie_goal && <Progress value={h.totals.calories} max={h.calorie_goal} warn={90} />}
        {h.medications.length > 0 && (
          <div className="chips top-gap">
            {h.medications.map((m: any) => (
              <span key={m.id} className={`chip ${m.planned && m.taken >= m.planned ? "done" : ""}`}>
                💊 {m.name} {m.taken}/{m.planned}
              </span>
            ))}
          </div>
        )}
      </Card>

      <Card title="🏋️ Неделя" action={<button className="link" onClick={() => go("sport")}>Подробнее</button>}>
        <div className="stats">
          <Stat label="Тренировок" value={fit.count} />
          <Stat label="Минут" value={fit.minutes} />
          <Stat label="Ккал" value={fit.calories} />
        </div>
      </Card>

      {data.goals.length > 0 && (
        <Card title="🎯 Цели">
          {data.goals.map((g: any) => (
            <div key={g.id} className="goal">
              <div className="between"><span>{g.title}</span>
                {g.target_value != null && <span className="muted small">{g.current_value ?? 0} / {g.target_value} {g.unit}</span>}
              </div>
              {g.target_value != null && <GoalProgress current={g.current_value} target={g.target_value} />}
            </div>
          ))}
        </Card>
      )}

      <Card title="⏰ Ближайшее" action={<button className="link" onClick={() => go("reminders")}>Все</button>}>
        {data.upcoming.length ? data.upcoming.map((r: any) => (
          <div key={r.id} className="list-row">
            <span>{r.text}</span><span className="muted small">{fmtDate(r.next_run_at)}</span>
          </div>
        )) : <Empty>Нет напоминаний на ближайшие сутки</Empty>}
      </Card>

      <button className="primary wide" onClick={() => go("ai")}>✨ Спросить Claude</button>
    </div>
  );
}
