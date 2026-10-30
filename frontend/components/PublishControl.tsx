"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { setVisibility, type Candidate } from "@/lib/api";

type Props = {
  candidate: Candidate;
  onChange: (candidate: Candidate) => void;
};

// Private by default (spec section 7). Stage 1: publishing is recorded only; nothing is shared.
export function PublishControl({ candidate, onChange }: Props) {
  const t = useTranslations("Publish");
  const [open, setOpen] = useState(false);
  const [creditDisplay, setCreditDisplay] = useState<"anonymous" | "name">("anonymous");
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function apply(body: Parameters<typeof setVisibility>[1]) {
    setBusy(true);
    setError(null);
    try {
      onChange(await setVisibility(candidate.candidate_id, body));
      setOpen(false);
      setConsent(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const published = candidate.visibility === "published";
  const creditText = candidate.credit
    ? candidate.credit.display === "name"
      ? t("creditName", { name: candidate.credit.name ?? "" })
      : t("creditAnonymous")
    : "";

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded border px-2 py-0.5 text-xs ${published ? "border-tag-dft text-tag-dft" : "border-line text-muted"}`}>
          {published ? `🌐 ${t("published")}` : `🔒 ${t("private")}`}
        </span>
        {published && <span className="text-xs text-muted">{creditText}</span>}
        {published ? (
          <button type="button" disabled={busy} className="text-xs underline" onClick={() => void apply({ visibility: "private" })}>
            {t("makePrivate")}
          </button>
        ) : (
          !open && (
            <button type="button" className="text-xs underline" onClick={() => setOpen(true)}>
              {t("publish")}
            </button>
          )
        )}
      </div>

      {open && !published && (
        <div className="rounded-md border border-line bg-background p-3">
          <p className="text-xs text-muted">{t("demoNote")}</p>
          <fieldset className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <legend className="sr-only">{t("credit")}</legend>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "anonymous"} onChange={() => setCreditDisplay("anonymous")} />
              {t("anonymous")}
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "name"} onChange={() => setCreditDisplay("name")} />
              {t("byName")}
            </label>
            {creditDisplay === "name" && (
              <input
                className="rounded border border-line bg-surface px-2 py-1"
                value={name}
                maxLength={200}
                placeholder={t("namePlaceholder")}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </fieldset>
          <label className="mt-2 flex items-start gap-2 text-xs">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            {t("consent", { id: candidate.candidate_id })}
          </label>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={busy || !consent || (creditDisplay === "name" && !name.trim())}
              className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              onClick={() =>
                void apply({ visibility: "published", credit_display: creditDisplay, display_name: name, consent })
              }
            >
              {t("confirm")}
            </button>
            <button type="button" className="text-xs underline" onClick={() => setOpen(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
