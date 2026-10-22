// Entity detayı sohbet paneli — AI ile streaming konuşma. Masaüstünde sağda sticky yan
// panel, mobilde bottom sheet içinde aynı bileşen (yüksekliği kapsayıcı belirler).
// suggestions: o entity'ye özel örnek soru çipleri (mesaj yokken panelin başında).
import React, { useRef, useState, useEffect } from "react";
import { MessageSquare, X } from "lucide-react";
import { streamChat } from "../api.js";
import { useI18n } from "../i18n.jsx";

export default function ChatPanel({ entityId, entityName, suggestions = [], onClose, className = "" }) {
  const { t } = useI18n();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    // Entity değişince sohbeti sıfırla.
    setMessages([]);
    setError(null);
  }, [entityId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function send(e, preset) {
    e?.preventDefault();
    const text = (preset ?? input).trim();
    if (!text || streaming) return;

    const history = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);
    setError(null);

    await streamChat({
      entityId,
      messages: history,
      onDelta: (delta) => {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: next[next.length - 1].content + delta,
          };
          return next;
        });
      },
      onError: (msg) => {
        setError(msg);
        setStreaming(false);
      },
      onDone: () => setStreaming(false),
    });
  }

  return (
    <div className={`flex min-h-0 flex-col rounded-xl border border-ink-600 bg-ink-800 ${className}`}>
      <div className="flex items-center gap-2 border-b border-ink-600 px-4 py-2 text-sm font-semibold text-slate-200">
        <MessageSquare className="h-4 w-4 shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate">{t("chat.title", { name: entityName })}</span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={t("chat.hide")}
            title={t("chat.hide")}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-ink-700 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          suggestions.length > 0 ? (
            <div className="flex flex-col items-start gap-2">
              {suggestions.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => send(null, q)}
                  disabled={streaming}
                  className="rounded-full border border-accent/30 bg-accent/5 px-3 py-1.5 text-left text-[13px] text-accent transition hover:bg-accent/15 disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">{t("chat.placeholderHint")}</p>
          )
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-accent/20 text-slate-100"
                  : "bg-ink-700 text-slate-200"
              }`}
            >
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
            </div>
          </div>
        ))}
        {error && <p className="text-xs text-rose-400">⚠ {error}</p>}
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-ink-600 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chat.ask")}
          disabled={streaming}
          className="flex-1 rounded-md border border-ink-500 bg-ink-900 px-3 py-2 text-base outline-none focus:border-accent disabled:opacity-60"
        />
        <button
          disabled={streaming || !input.trim()}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-fg disabled:opacity-50"
        >
          {streaming ? "…" : t("chat.send")}
        </button>
      </form>
    </div>
  );
}
