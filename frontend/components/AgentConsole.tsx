"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { runAgent, type AgentResult } from "@/lib/api";

export function AgentConsole() {
  const t = useTranslations("Agent");
  const locale = useLocale();
  const [message, setMessage] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await runAgent(message, locale));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>
      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
        <input
          className="flex-1 rounded-md border border-line bg-background px-3 py-2"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={t("placeholder")}
        />
        <button
          type="submit"
          disabled={running || !message.trim()}
          className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {running ? t("running") : t("run")}
        </button>
      </form>

      {error && <p className="mt-3 text-danger">{t("error", { message: error })}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <div>
            <h3 className="text-sm font-semibold">{t("answer")}</h3>
            <p className="whitespace-pre-wrap">{result.output_text}</p>
          </div>
          <div>
            <h3 className="text-sm font-semibold">
              {t("toolCalls", { count: result.tool_calls.length })}
            </h3>
            {result.tool_calls.length === 0 ? (
              <p className="text-sm text-warning">{t("noToolCalls")}</p>
            ) : (
              result.tool_calls.map((call, index) => (
                <details key={index} className="mt-1 rounded-md border border-line p-2">
                  <summary className="cursor-pointer font-mono text-sm">
                    {call.name}({call.arguments})
                  </summary>
                  <pre className="mt-2 overflow-x-auto text-xs">
                    {JSON.stringify(call.output, null, 2)}
                  </pre>
                </details>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  );
}
