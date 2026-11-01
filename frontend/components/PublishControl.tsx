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
        <span key={m.candidate_id} className="whitespace-nowrap">
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
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded border px-2 py-0.5 text-xs ${published ? "border-tag-dft text-tag-dft" : "border-line text-muted"}`}>
          {published ? `🌐 ${t("published")}` : t("private")}
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

      {open && !published && (
        <div className="subcard">
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
            {t("consent", { id: candidate.candidate_id })}
          </label>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={busy || !consent || (creditDisplay === "name" && !name.trim())}
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

/** In the candidate's card, with sign-in on: is this material public, and can you make it public? */
export function PublicStatus({ candidate, onChange }: Props) {
  const t = useTranslations("Publish");
  const { name: accountName } = useAuth();
  const [matches, setMatches] = useState<PublicMatches | null>(null);
  const [open, setOpen] = useState(false);
  const [creditDisplay, setCreditDisplay] = useState<"anonymous" | "name">("name");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const published = candidate.visibility === "published";
  const owned = candidate.mine;
  const check = owned && !published;

  useEffect(() => {
    if (!check) return;
    let active = true;
    setMatches(null);
    getPublicMatches(candidate.candidate_id)
      .then((found) => active && setMatches(found))
      .catch((err) => active && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      active = false;
    };
  }, [check, candidate.candidate_id]);

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

  if (!candidate.editable) return <p className="text-xs text-muted">{t("otherNote")}</p>;
  if (!owned) {
    return (
      <p className="text-xs text-muted">
        {t("publicChipHint")} {t("publicHint")}
      </p>
    );
  }
  if (published) {
    const hash = candidate.credit?.content_sha256;
    return (
      <div className="text-xs text-muted">
        <button type="button" disabled={busy} className="mr-2 underline" onClick={() => void apply({ visibility: "private" })}>
          {t("makePrivate")}
        </button>
        {t("undoNote")} {hash && t("recordHash", { hash: hash.slice(0, 16) })}
        {error && <p className="mt-1 text-danger">{error}</p>}
      </div>
    );
  }

  const taken = (matches?.already_public.length ?? 0) > 0;
  const tag = accountName ?? "";
  const makePublic = creditDisplay === "name" ? t("makePublic", { name: tag }) : t("makePublicAnonymous");
  return (
    <div className="space-y-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2" aria-live="polite">
        {!matches && !error && <p className="text-muted">{t("checking")}</p>}
        {matches && taken && (
          <p className="text-warning">
            {t("duplicate")} <MatchList matches={matches.already_public} />
          </p>
        )}
        {matches && !taken && (
          <p className="text-accent-text">✓ {t(matches.unclaimed.length ? "noDuplicate" : "notPublic")}</p>
        )}
        {matches && !taken && !open && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>
            {t("makePublic", { name: tag })}
          </button>
        )}
      </div>
      {matches && matches.other_framework.length > 0 && (
        <p className="text-muted">
          {t("otherFramework")} <MatchList matches={matches.other_framework} />
        </p>
      )}
      {open && matches && !taken && (
        <div className="subcard">
          {matches.unclaimed.length > 0 && (
            <p className="mb-2 text-muted">
              {t("unclaimed")} <MatchList matches={matches.unclaimed.slice(0, 5)} />
            </p>
          )}
          <p className="text-muted">{t("ownedWarning")}</p>
          <fieldset className="mt-2 flex flex-wrap items-center gap-3">
            <legend className="sr-only">{t("credit")}</legend>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "name"} onChange={() => setCreditDisplay("name")} />
              {t("creditLogin", { name: tag })}
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={creditDisplay === "anonymous"} onChange={() => setCreditDisplay("anonymous")} />
              {t("anonymousOwned")}
            </label>
          </fieldset>
          <label className="mt-2 flex items-start gap-2">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            {t("consentOwned", { id: candidate.candidate_id })}
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy || !consent}
              className="btn btn-primary btn-sm"
              onClick={() => void apply({ visibility: "published", credit_display: creditDisplay, consent })}
            >
              {makePublic}
            </button>
            <button type="button" className="underline" onClick={() => setOpen(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
      {error && <p className="text-danger">{error}</p>}
    </div>
  );
}
