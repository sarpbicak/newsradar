// Entity detayı içindeki sohbet paneli — AI ile streaming konuşma.
import React, { useRef, useState, useEffect } from "react";
import { streamChat } from "../api.js";
import { useI18n } from "../i18n.jsx";

export default function ChatPanel({ entityId, entityName }) {
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

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
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
    <div className="flex h-[520px] flex-col rounded-xl border border-ink-600 bg-ink-800">
      <div className="border-b border-ink-600 px-4 py-2 text-sm font-semibold text-slate-200">
        💬 {t("chat.title", { name: entityName })}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-500">
            {t("chat.placeholderHint")}
          </p>
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
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {streaming ? "…" : t("chat.send")}
        </button>
      </form>
    </div>
  );
}
