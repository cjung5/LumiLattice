"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { searchLiterature, type LiteratureResult } from "@/lib/api";

// The parent gives this panel a `key` per formula, so the query resets when the host changes.
export function LiteraturePanel({ formula }: { formula: string | null }) {
  const t = useTranslations("Literature");
  const [query, setQuery] = useState(formula ? `${formula} refractive index` : "");
  const [result, setResult] = useState<LiteratureResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await searchLiterature(query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const papers = result?.papers;
  const failed = Object.entries(result?.source_status ?? {}).filter(([, status]) => status !== "ok");

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>
      <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
        <input
          className="flex-1 rounded-md border border-line bg-background px-3 py-2"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("placeholder")}
        />
        <button
          type="submit"
          disabled={loading || query.trim().length < 2}
          className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {loading ? t("searching") : t("search")}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      {failed.length > 0 && (
        <p className="mt-2 text-xs text-warning">
          {failed.map(([name, status]) => t("sourceFailed", { source: name, reason: status })).join(" ")}
        </p>
      )}
      {papers && papers.length === 0 && <p className="mt-3 text-sm text-muted">{t("empty")}</p>}

      {papers && papers.length > 0 && (
        <ol className="mt-3 space-y-3">
          {papers.map((paper) => (
            <li key={paper.doi ?? paper.provenance.reference ?? paper.title} className="text-sm">
              {paper.url ? (
                <a href={paper.url} target="_blank" rel="noreferrer" className="font-medium text-accent underline">
                  {paper.title}
                </a>
              ) : (
                <span className="font-medium">{paper.title}</span>
              )}
              <div className="text-muted">
                {[
                  paper.authors.length ? `${paper.authors.join(", ")}${paper.authors.length >= 3 ? " et al." : ""}` : null,
                  paper.year,
                  paper.venue,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                {paper.doi && <span className="font-mono">doi:{paper.doi}</span>}
                {paper.cited_by_count != null && <span>{t("citedBy", { count: paper.cited_by_count })}</span>}
                {paper.open_access && paper.open_access_url && (
                  <a href={paper.open_access_url} target="_blank" rel="noreferrer" className="underline">
                    {t("openAccess")}
                  </a>
                )}
                {(paper.sources.length ? paper.sources : [paper.provenance.source]).map((source) => (
                  <span key={source} className="rounded border border-line px-1">
                    {source}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
