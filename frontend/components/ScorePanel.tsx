"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { EvidenceTag } from "@/components/EvidenceTag";
import { useLevel } from "@/components/Level";
import { getScorecard, type Candidate, type Goal, type MetricId, type Scorecard } from "@/lib/api";

// One request per candidate and goal: the panel and the leaderboard share it.
const cache = new Map<string, Promise<Scorecard>>();

function loadScore(id: string, goal: Goal): Promise<Scorecard> {
  const key = `${id}|${JSON.stringify(goal)}`;
  let request = cache.get(key);
  if (!request) {
    request = getScorecard(id, goal).catch((err) => {
      cache.delete(key);
      throw err;
    });
    cache.set(key, request);
  }
  return request;
}

const fmt = (low: number, high: number) => {
  const [a, b] = [Math.round(low), Math.round(high)];
  return a === b ? `${a}` : `${a}–${b}`;
};

function RangeBar({ low, high, mark }: { low: number; high: number; mark?: boolean }) {
  return (
    <div className="relative h-2 w-full rounded-full bg-line">
      <div
        className={`absolute inset-y-0 min-w-1.5 rounded-full ${mark ? "bg-accent" : "bg-muted"}`}
        style={{ left: `${low}%`, width: `${high - low}%` }}
      />
    </div>
  );
}

// Sent to the research agent in English; it replies in the UI language.
const raisePrompt = (id: string, metric: MetricId) =>
  `Suggest and test one change to ${id} that raises its ${metric} score in get_scorecard. Then compare the two scorecards and say what got worse.`;

type Props = {
  candidate: Candidate;
  goal: Goal;
  onAskAgent?: (message: string, shown?: string) => void;
};

export function ScorePanel({ candidate, goal, onAskAgent }: Props) {
  const t = useTranslations("Scorecard");
  const guided = useLevel().level === "guided";
  const id = candidate.candidate_id;
  const key = `${id}|${JSON.stringify(goal)}`;
  const [state, setState] = useState<{ key: string; card?: Scorecard; error?: string } | null>(null);

  useEffect(() => {
    let active = true;
    loadScore(id, goal)
      .then((card) => active && setState({ key, card }))
      .catch((err) => active && setState({ key, error: err instanceof Error ? err.message : String(err) }));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const current = state?.key === key ? state : null;
  if (current?.error) return <p className="text-sm text-danger">{current.error}</p>;
  if (!current?.card) return <p className="text-sm text-muted">{t("loading")}</p>;
  const card = current.card;
  const bench = card.benchmark;
  const rows = [
    ...bench.landmarks.filter((e) => e.formula !== id).map((e) => ({ label: e.formula, low: e.score, high: e.score, kind: "known" as const })),
    { label: id, low: card.optical_low, high: card.optical_high, kind: "candidate" as const },
  ].sort((a, b) => b.high + b.low - (a.high + a.low));
  const host = bench.host?.formula;

  return (
    <section className="space-y-4 rounded-md border border-line p-4 text-sm" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
          <span className="text-3xl font-bold tabular-nums">{fmt(card.low, card.high)}</span>
          <span className="text-muted">{t("outOf")}</span>
        </div>
        <div className="mt-2 max-w-md">
          <RangeBar low={card.low} high={card.high} mark />
        </div>
        {card.disqualified.length > 0 && (
          <p className="mt-2 font-medium text-danger">
            <span aria-hidden>✗ </span>
            {t("disqualified", { elements: card.disqualified.join(", ") })}
          </p>
        )}
        <p className="mt-2 text-xs text-muted">{t("notProbability")}</p>
        <p className="mt-1 text-xs">
          {t("evidenceShare")}{" "}
          {Object.entries(card.evidence_mix).map(([status, share]) => (
            <span key={status} className="mr-2 whitespace-nowrap">
              {t(`evidence.${status}`)} {share}%
            </span>
          ))}
        </p>
      </div>

      <div>
        <h4 className="font-medium">{t("metricsTitle")}</h4>
        <ul className="mt-2 space-y-3">
          {card.metrics.map((m) => (
            <li key={m.id}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                <span className="font-medium">
                  {t(`metric.${m.id}.name`)}
                  {m.id === card.biggest_gain && (
                    <span className="ml-2 rounded border border-accent px-1 text-xs font-normal text-accent">{t("mostToGain")}</span>
                  )}
                </span>
                <span className="text-xs tabular-nums">
                  {t("points", { score: fmt(m.low, m.high), weight: m.weight })}
                </span>
              </div>
              <div className="my-1">
                <RangeBar low={m.low} high={m.high} mark={m.id === card.biggest_gain} />
              </div>
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                {m.value && <span className="tabular-nums">{m.value}</span>}
                {m.evidence === "Model" ? <span className="text-muted">{t("evidence.Model")}</span> : <EvidenceTag status={m.evidence} />}
              </p>
              <p className="mt-0.5 text-xs text-muted">{guided ? t(`metric.${m.id}.why`) : m.detail}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded border border-accent p-3">
        <h4 className="font-medium">{t("gainTitle", { metric: t(`metric.${card.biggest_gain}.name`) })}</h4>
        <p className="mt-1">{t(`metric.${card.biggest_gain}.gain`)}</p>
        {onAskAgent && (
          <button
            type="button"
            onClick={() => onAskAgent(raisePrompt(id, card.biggest_gain), t("raise", { metric: t(`metric.${card.biggest_gain}.name`) }))}
            className="mt-2 rounded-md border border-accent px-3 py-1 font-medium text-accent"
          >
            {t("raise", { metric: t(`metric.${card.biggest_gain}.name`) })}
          </button>
        )}
      </div>

      <div>
        <h4 className="font-medium">{t("benchmarkTitle")}</h4>
        <p className="mt-1">
          {t("beats", { low: bench.beats_low, high: bench.beats_high, size: bench.size, range: bench.beats_low === bench.beats_high ? `${bench.beats_low}` : `${bench.beats_low}–${bench.beats_high}` })}
        </p>
        <ul className="mt-2 space-y-1 text-xs">
          {rows.map((row) => (
            <li key={row.label} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-2">
              <span className={row.kind === "candidate" ? "truncate font-semibold" : "truncate"}>
                {row.label}
                {row.label === host && <span className="text-muted"> {t("start")}</span>}
              </span>
              <RangeBar low={row.low} high={row.high} mark={row.kind === "candidate"} />
              <span className={`text-right tabular-nums ${row.kind === "candidate" ? "font-semibold" : ""}`}>{fmt(row.low, row.high)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">{bench.note}</p>
      </div>

      <details className="text-xs">
        <summary className="cursor-pointer text-muted">{t("howScored")}</summary>
        <p className="mt-1">{card.method}</p>
      </details>
    </section>
  );
}

type BoardProps = {
  candidates: Candidate[];
  current: string;
  goal: Goal;
  onSelect: (candidate: Candidate) => void;
};

/** Every candidate from this session, best first, so each attempt shows progress. */
export function Leaderboard({ candidates, current, goal, onSelect }: BoardProps) {
  const t = useTranslations("Scorecard");
  const [cards, setCards] = useState<Record<string, Scorecard>>({});
  const key = `${candidates.map((c) => c.candidate_id).join(",")}|${JSON.stringify(goal)}`;

  useEffect(() => {
    let active = true;
    Promise.all(candidates.map((c) => loadScore(c.candidate_id, goal).catch(() => null))).then((results) => {
      if (active) setCards(Object.fromEntries(results.filter((r): r is Scorecard => !!r).map((r) => [r.subject, r])));
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const middle = (id: string) => {
    const card = cards[id];
    if (!card) return -1;
    return card.disqualified.length ? -0.5 : (card.low + card.high) / 2;
  };
  const ranked = [...candidates].sort((a, b) => middle(b.candidate_id) - middle(a.candidate_id));

  return (
    <section className="rounded-md border border-line p-4 text-sm" aria-label={t("boardTitle")}>
      <h3 className="font-semibold">{t("boardTitle")}</h3>
      <p className="mt-1 text-xs text-muted">{t("boardHint")}</p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-muted">
            <tr>
              <th className="py-1 pr-2 font-normal">#</th>
              <th className="py-1 pr-2 font-normal">{t("boardCandidate")}</th>
              <th className="py-1 pr-2 font-normal">{t("boardScore")}</th>
              <th className="w-1/3 py-1 font-normal">{t("boardRange")}</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {ranked.map((c, i) => {
              const card = cards[c.candidate_id];
              return (
                <tr key={c.candidate_id} className={`border-t border-line ${c.candidate_id === current ? "font-semibold" : ""}`}>
                  <td className="py-1 pr-2">{i + 1}</td>
                  <td className="py-1 pr-2">
                    <button type="button" onClick={() => onSelect(c)} className="text-left underline-offset-2 hover:underline">
                      {c.candidate_id} {c.formula}
                    </button>
                  </td>
                  <td className="py-1 pr-2">
                    {card ? fmt(card.low, card.high) : "…"}
                    {card?.disqualified.length ? <span className="text-danger"> ✗</span> : null}
                  </td>
                  <td className="py-1">{card && <RangeBar low={card.low} high={card.high} mark={c.candidate_id === current} />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
