import { useEffect, useRef, useState } from "react";
import { api, confirmAction, haptic } from "../api";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "Как у меня с бюджетом в этом месяце?",
  "Сколько калорий я съел сегодня?",
  "Составь план тренировок на неделю",
  "Кому я должен и сколько?",
];

// Безопасный минимальный markdown: экранируем HTML, потом **жирный** и переносы
function md(text: string) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^\s*[-*]\s+/gm, "• ").replace(/\n/g, "<br/>");
}

export default function Assistant() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.get<Msg[]>("/ai/history").then(setMsgs).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const push = (m: Msg) => setMsgs((prev) => [...prev, m]);

  const send = async (message = text) => {
    if (!message.trim() || busy) return;
    setText(""); push({ role: "user", content: message }); setBusy(true);
    try {
      const r = await api.post("/ai/chat", { message });
      push({ role: "assistant", content: r.reply }); haptic("success");
    } catch (e: any) { push({ role: "assistant", content: `⚠️ ${e.message}` }); haptic("error"); }
    setBusy(false);
  };

  const upload = async (file: Blob, name: string, label: string) => {
    const fd = new FormData();
    fd.append("file", file, name);
    fd.append("message", text);
    push({ role: "user", content: `${label}${text ? " " + text : ""}` });
    setText(""); setBusy(true);
    try {
      const r = await api.post("/ai/upload", fd);
      if (r.transcript) setMsgs((prev) => [...prev.slice(0, -1), { role: "user", content: `🎙 ${r.transcript}` }]);
      push({ role: "assistant", content: r.reply }); haptic("success");
    } catch (e: any) { push({ role: "assistant", content: `⚠️ ${e.message}` }); }
    setBusy(false);
  };

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) upload(f, f.name, f.type === "application/pdf" ? `📄 ${f.name}` : "📷 Фото");
    e.target.value = "";
  };

  const toggleVoice = async () => {
    if (recording) { recRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const type = rec.mimeType || "audio/webm";
        upload(new Blob(chunks, { type }), type.includes("mp4") ? "voice.m4a" : "voice.webm", "🎙 Голосовое…");
      };
      recRef.current = rec; rec.start(); setRecording(true); haptic();
    } catch {
      push({ role: "assistant", content: "Нет доступа к микрофону. Голосовые можно отправлять прямо в чат с ботом 🎙" });
    }
  };

  const clear = async () => {
    if (!(await confirmAction("Очистить переписку? Записи о расходах, еде и т.д. останутся."))) return;
    await api.del("/ai/history"); setMsgs([]);
  };

  return (
    <div className="page chat-page">
      <div className="between">
        <h1>Claude</h1>
        {msgs.length > 0 && <button className="link" onClick={clear}>Очистить</button>}
      </div>
      <div className="chat">
        {msgs.length === 0 && (
          <div className="suggestions">
            <p className="muted">Пиши как другу: «потратил 1200 на такси», «съел шаурму», «выпил таблетку». Или спроси что-нибудь:</p>
            {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`} dangerouslySetInnerHTML={{ __html: md(m.content) }} />
        ))}
        {busy && <div className="bubble assistant typing"><span /><span /><span /></div>}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
        <button className="icon big" onClick={() => fileRef.current?.click()} disabled={busy} title="Чек или документ">📎</button>
        <textarea rows={1} value={text} placeholder="Сообщение…" onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        {text.trim()
          ? <button className="primary round" onClick={() => send()} disabled={busy}>➤</button>
          : <button className={`primary round ${recording ? "rec" : ""}`} onClick={toggleVoice} disabled={busy}>{recording ? "■" : "🎙"}</button>}
      </div>
    </div>
  );
}
