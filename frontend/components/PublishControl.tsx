"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/Auth";
import { LockIcon } from "@/components/LockIcon";
import { getPublicMatches, setVisibility, type Candidate, type Credit, type PublicMatch, type PublicMatches } from "@/lib/api";

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

/** Below the candidate's name: whose it is, and who can see it. */
export function OwnershipLine({ candidate }: { candidate: Candidate }) {
  const t = useTranslations("Publish");
  const creditText = useCreditText();
  const { enabled } = useAuth();
  const based = candidate.based_on_credit;
  const basedOn =
    based && (based.display === "name" && based.name ? t("basedOn", { name: based.name }) : t("basedOnAnonymous"));
  const badge = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium";
  const hasBadge = candidate.credit || candidate.mine || enabled;
  if (!hasBadge && !basedOn) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted">
      {candidate.credit ? (
        <span className={`${badge} border-tag-dft text-tag-dft`}>🌐 {creditText(candidate.credit)}</span>
      ) : candidate.mine ? (
        <span className={`${badge} border-accent bg-accent-soft text-accent-text`} title={t("privateHint")}>
          <LockIcon />
          {t("privateChip")}
        </span>
      ) : enabled ? (
        <span className={`${badge} border-line-strong`} title={t("publicChipHint")}>
          {t("publicChip")}
        </span>
      ) : null}
      {basedOn && <span>{basedOn}</span>}
    </div>
  );
}

function MatchList({ matches }: { matches: PublicMatch[] }) {
  const t = useTranslations("Publish");
  return (
    <>
      {matches.map((m, i) => (
        <span key={m.candidate_id}>
          {i > 0 && ", "}
          <a className="text-accent-text underline" href={`?candidate=${encodeURIComponent(m.candidate_id)}`}>
            {m.candidate_id}
          </a>
          {m.credit && ` (${m.credit.display === "name" && m.credit.name ? m.credit.name : t("anonymous")})`}
        </span>
      ))}
    </>
  );
}

// A candidate from private mode has an owner, who alone can publish it, under the account's tag.
// With sign-in off, the app works as a demo: publishing records a typed name (spec section 7).
export function PublishControl({ candidate, onChange }: Props) {
  const t = useTranslations("Publish");
  const creditText = useCreditText();
  const { enabled, name: accountName } = useAuth();
  const [open, setOpen] = useState(false);
  const [creditDisplay, setCreditDisplay] = useState<"anonymous" | "name">(candidate.mine ? "name" : "anonymous");
  const [matches, setMatches] = useState<PublicMatches | null>(null);
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
  const checkMatches = open && candidate.mine && !published;

  useEffect(() => {
    if (!checkMatches) return;
    let active = true;
    setMatches(null);
    getPublicMatches(candidate.candidate_id)
      .then((found) => active && setMatches(found))
      .catch((err) => active && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [checkMatches, candidate.candidate_id]);

  const taken = (matches?.already_public.length ?? 0) > 0;

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
        <p className="text-xs text-muted">
          {t("publicChipHint")} {t("publicHint")}
        </p>
      </div>
    );
  }

  const owned = candidate.mine;
  const hash = candidate.credit?.content_sha256;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${published ? "border-tag-dft text-tag-dft" : "border-line text-muted"}`}>
          {published ? (
            `🌐 ${t("published")}`
          ) : owned ? (
            <>
              <LockIcon />
              {t("privateChip")}
            </>
          ) : (
            t("private")
          )}
        </span>
        {!published && owned && <span className="text-xs text-muted">{t("privateHint")}</span>}
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
          {owned && (
            <div className="mb-2 text-xs" aria-live="polite">
              {!matches && !error && <p className="text-muted">{t("checking")}</p>}
              {matches && taken && (
                <p className="text-warning">
                  {t("duplicate")} <MatchList matches={matches.already_public} />
                </p>
              )}
              {matches && !taken && <p className="text-accent-text">✓ {t("noDuplicate")}</p>}
              {matches && matches.other_framework.length > 0 && (
                <p className="mt-1 text-muted">
                  {t("otherFramework")} <MatchList matches={matches.other_framework} />
                </p>
              )}
              {matches && !taken && matches.unclaimed.length > 0 && (
                <p className="mt-1 text-muted">
                  {t("unclaimed")} <MatchList matches={matches.unclaimed.slice(0, 5)} />
                </p>
              )}
            </div>
          )}
          <p className="text-xs text-muted">{owned ? t("ownedWarning") : t("demoNote")}</p>
          <fieldset className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <legend className="sr-only">{t("credit")}</legend>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "anonymous"} onChange={() => setCreditDisplay("anonymous")} />
              {owned ? t("anonymousOwned") : t("anonymous")}
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "name"} onChange={() => setCreditDisplay("name")} />
              {owned ? t("creditLogin", { name: accountName ?? "" }) : t("byName")}
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
              disabled={busy || !consent || (!owned && creditDisplay === "name" && !name.trim()) || (owned && (!matches || taken))}
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
