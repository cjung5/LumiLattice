"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import type { ToolCall } from "@/lib/api";

export type AgentTurn =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; toolCalls: ToolCall[]; candidateIds: string[] };

type Props = {
  turns: AgentTurn[];
  busy: boolean;
  error: string | null;
  onSend: (message: string) => void;
  onReset: () => void;
  onOpenCandidate: (candidateId: string) => void;
};

export function AgentPanel({ turns, busy, error, onSend, onReset, onOpenCandidate }: Props) {
  const t = useTranslations("Agent");
  const [message, setMessage] = useState("");

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    onSend(message.trim());
    setMessage("");
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">{t("title")}</h2>
        {turns.length > 0 && (
          <button type="button" onClick={onReset} disabled={busy} className="text-sm text-muted underline">
            {t("reset")}
          </button>
        )}
      </div>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>

      <ol className="space-y-3">
        {turns.map((turn, index) =>
          turn.role === "user" ? (
            <li key={index} className="ml-8 rounded-md bg-background px-3 py-2 text-sm">
              {turn.text}
            </li>
          ) : (
            <li key={index} className="space-y-2">
              <p className="whitespace-pre-wrap text-sm">{turn.text}</p>
              {turn.candidateIds.length > 0 && (
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="text-muted">{t("created")}</span>
                  {turn.candidateIds.map((id) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => onOpenCandidate(id)}
                      className="rounded border border-accent px-1.5 font-mono text-accent"
                    >
                      {id}
                    </button>
                  ))}
                </div>
              )}
              {turn.toolCalls.length === 0 ? (
                <p className="text-xs text-warning">{t("noToolCalls")}</p>
              ) : (
                <details className="rounded-md border border-line p-2 text-xs">
                  <summary className="cursor-pointer">{t("toolCalls", { count: turn.toolCalls.length })}</summary>
                  {turn.toolCalls.map((call, i) => (
                    <details key={i} className="mt-1 rounded border border-line p-1">
                      <summary className="cursor-pointer font-mono">
                        {call.name}({call.arguments})
                      </summary>
                      <pre className="mt-1 overflow-x-auto">{JSON.stringify(call.output, null, 2)}</pre>
                    </details>
                  ))}
                </details>
              )}
            </li>
          ),
        )}
      </ol>

      {busy && <p className="mt-3 text-sm text-muted">{t("running")}</p>}
      {error && <p className="mt-3 text-sm text-danger">{t("error", { message: error })}</p>}

      <form onSubmit={onSubmit} className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          className="flex-1 rounded-md border border-line bg-background px-3 py-2"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={t("placeholder")}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !message.trim()}
          className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {busy ? t("running") : t("run")}
        </button>
      </form>
    </section>
  );
}
