// Ask AI paneli — AI ile streaming konuşma. Masaüstünde sağda sabit yan panel (yükseltilmiş
// yüzey), mobilde alttan açılan sayfa içinde aynı bileşen (yüksekliği kapsayıcı belirler).
// Mesaj balonları ortak stil; örnek sorular ikincil çip; gönder birincil buton; cevap akarken
// yanıp sönen imleç (reduced-motion'da sabit).
// suggestions: o entity'ye özel örnek soru çipleri (mesaj yokken panelin başında).
import React, { useRef, useState, useEffect } from "react";
import { MessageSquare, X } from "lucide-react";
import { streamChat } from "../api.js";
import { useI18n } from "../i18n.jsx";
import { Button, ChipButton, Input, cx } from "./kit.jsx";

// bare: kendi yüzeyi yok (mobilde alttan sayfa Modal'ının içinde).
export default function ChatPanel({ entityId, entityName, suggestions = [], onClose, className = "", bare = false }) {
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

  const last = messages.length - 1;
  return (
    <div className={cx("flex min-h-0 flex-col", !bare && "rounded-card bg-raised shadow-card ring-1 ring-ink-600", className)}>
      <div className="flex items-center gap-2 border-b border-ink-600 px-4 py-3">
        <MessageSquare className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
        <h2 className="min-w-0 flex-1 truncate font-display text-sm font-semibold text-slate-100">{t("chat.title", { name: entityName })}</h2>
        {onClose && <Button variant="ghost" size="sm" iconOnly icon={X} onClick={onClose} aria-label={t("chat.hide")} title={t("chat.hide")} />}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {messages.length === 0 &&
          (suggestions.length > 0 ? (
            <div className="flex flex-col items-start gap-2">
              {suggestions.map((q) => (
                <ChipButton key={q} onClick={() => send(null, q)} disabled={streaming} className="whitespace-normal">
                  {q}
                </ChipButton>
              ))}
            </div>
          ) : (
            <p className="text-meta text-slate-500">{t("chat.placeholderHint")}</p>
          ))}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={cx(
                "max-w-[88%] whitespace-pre-wrap rounded-control px-3.5 py-2.5 text-body",
                m.role === "user" ? "bg-accent/15 text-slate-100" : "bg-ink-700 text-slate-200",
                m.role === "assistant" && streaming && i === last && "caret"
              )}
            >
              {m.content}
            </div>
          </div>
        ))}
        {error && <p className="text-meta text-rose-600">{error}</p>}
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-ink-600 p-3">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("chat.ask")} disabled={streaming} aria-label={t("chat.ask")} className="flex-1" />
        <Button type="submit" variant="primary" disabled={streaming || !input.trim()}>
          {streaming ? "…" : t("chat.send")}
        </Button>
      </form>
    </div>
  );
}
