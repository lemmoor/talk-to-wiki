"use client";

import { useState, useRef, useEffect } from "react";
import { FaArrowRight } from "react-icons/fa";

type Source = {
  url: string;
  title: string;
};

type Message = {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
};

export default function ChatBox() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit() {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    const userMessage: Message = { role: "user", text: trimmed };
    setMessages([userMessage]);
    setQuery("");
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Something went wrong.");
      }
      const data = await res.json();
      setMessages([
        userMessage,
        {
          role: "assistant",
          text: data.response.answer,
          sources: data.response.sources,
        },
      ]);
    } catch (e) {
      setMessages([
        userMessage,
        {
          role: "assistant",
          text: e instanceof Error ? e.message : "Something went wrong. Sorry :(",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full flex flex-col rounded-2xl bg-[rgb(209_248_255/20%)] backdrop-blur-sm shadow-lg overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-md px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-[rgb(0_21_64)] text-white"
                  : "bg-white/20 text-slate-200"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.text}</p>
              {msg.sources && msg.sources.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-1 pt-3 ">
                  {msg.sources.map((source, j) => (
                    <a
                      key={j}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block rounded-full bg-[rgb(0_21_64/50%)] px-3 py-1 text-xs text-slate-200 hover:bg-[rgb(0_21_64/70%)] transition-colors underline"
                    >
                      {source.title}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-md px-4 py-3 bg-white/10 text-sm text-slate-400 animate-pulse">
              Thinking...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2 p-4 border-t border-white/10">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
          placeholder="Ask a question..."
          className="flex-1 rounded-md bg-white/10 border border-white/20 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-400 focus:border-white/40"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading || !query.trim()}
          className="rounded-md border cursor-pointer border-white/20 bg-transparent px-4 py-3 text-sm text-white transition-colors hover:border-white/40 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <FaArrowRight />
        </button>
      </div>
    </div>
  );
}
