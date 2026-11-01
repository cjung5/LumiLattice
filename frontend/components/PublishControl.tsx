"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { useAuth } from "@/components/Auth";
import { setVisibility, type Candidate, type Credit } from "@/lib/api";

type Props = {
  candidate: Candidate;
  onChange: (candidate: Candidate) => void;
};

function useCreditText() {
  const t = useTranslations("Publish");
  const locale = useLocale();
  return (credit: Credit) => {
    const date = new Date(credit.published_at).toLocaleDateString(locale, { dateStyle: "medium" });
    const who = credit.verified
      ? t("creditVerified", { name: credit.name ?? "" })
      : credit.display === "name"
        ? t("creditName", { name: credit.name ?? "" })
        : t("creditAnonymous");
    return [who, date, credit.license ? t("license", { license: credit.license }) : ""].filter(Boolean).join(" · ");
  };
}

/** Beside the candidate's name: whose it is, and who can see it. */
export function OwnershipLine({ candidate }: { candidate: Candidate }) {
  const t = useTranslations("Publish");
  const creditText = useCreditText();
  const { enabled } = useAuth();
  const parts: string[] = [];
  if (candidate.credit) parts.push(creditText(candidate.credit));
  else if (candidate.mine) parts.push(`🔒 ${t("privateChip")}`);
  else if (enabled) parts.push(t("publicChip"));
  if (candidate.based_on_credit) {
    parts.push(
      candidate.based_on_credit.display === "name" && candidate.based_on_credit.name
        ? t("basedOn", { name: candidate.based_on_credit.name })
        : t("basedOnAnonymous"),
    );
  }
  return parts.length ? <p className="text-xs text-muted">{parts.join(" · ")}</p> : null;
}

// A candidate from private mode has an owner, who alone can publish it, under the signed-in name.
// With sign-in off, the app works as a demo: publishing records a typed name (spec section 7).
export function PublishControl({ candidate, onChange }: Props) {
  const t = useTranslations("Publish");
  const creditText = useCreditText();
  const { enabled, login } = useAuth();
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

  // Someone else's published work: read it, or revise it into your own version.
  if (!candidate.editable) {
    return (
      <div className="flex flex-col gap-1 text-sm">
        <span className="w-fit rounded border border-tag-dft px-2 py-0.5 text-xs text-tag-dft">🌐 {t("published")}</span>
        {candidate.credit && <p className="text-xs text-muted">{creditText(candidate.credit)}</p>}
        <p className="text-xs text-muted">{t("otherNote")}</p>
      </div>
    );
  }

  // Public mode with sign-in on: no owner, so nobody can claim it.
  if (enabled && !candidate.mine) {
    return (
      <div className="flex flex-col gap-1 text-sm">
        <span className="w-fit rounded border border-line px-2 py-0.5 text-xs text-muted">{t("publicChip")}</span>
        <p className="text-xs text-muted">{t("publicHint")}</p>
      </div>
    );
  }

  const owned = candidate.mine;
  const hash = candidate.credit?.content_sha256;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded border px-2 py-0.5 text-xs ${published ? "border-tag-dft text-tag-dft" : "border-line text-muted"}`}>
          {published ? `🌐 ${t("published")}` : owned ? `🔒 ${t("privateChip")}` : t("private")}
        </span>
        {published && candidate.credit && <span className="text-xs text-muted">{creditText(candidate.credit)}</span>}
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
      {published && owned && (
        <p className="text-xs text-muted">
          {t("undoNote")} {hash && t("recordHash", { hash: hash.slice(0, 16) })}
        </p>
      )}

      {open && !published && (
        <div className="subcard">
          <p className="text-xs text-muted">{owned ? t("ownedWarning") : t("demoNote")}</p>
          <fieldset className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <legend className="sr-only">{t("credit")}</legend>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "anonymous"} onChange={() => setCreditDisplay("anonymous")} />
              {owned ? t("anonymousOwned") : t("anonymous")}
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "name"} onChange={() => setCreditDisplay("name")} />
              {owned ? t("creditLogin", { login: login ?? "" }) : t("byName")}
            </label>
            {!owned && creditDisplay === "name" && (
              <input
                className="field"
                value={name}
                maxLength={200}
                placeholder={t("namePlaceholder")}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </fieldset>
          <label className="mt-2 flex items-start gap-2 text-xs">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            {owned ? t("consentOwned", { id: candidate.candidate_id }) : t("consent", { id: candidate.candidate_id })}
          </label>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={busy || !consent || (!owned && creditDisplay === "name" && !name.trim())}
              className="btn btn-primary btn-sm"
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
