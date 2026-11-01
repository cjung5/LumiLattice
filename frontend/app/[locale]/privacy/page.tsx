import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";
import { use } from "react";

export const metadata: Metadata = { title: "Privacy | LumiLattice" };

const REPOSITORY = "https://github.com/cjung5/LumiLattice";

// In English only: a machine translation of what happens to someone's data could mislead them.
export default function PrivacyPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  setRequestLocale(locale);
  const heading = "mt-6 font-semibold";
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 text-sm sm:px-6">
      <h1 className="text-xl font-semibold tracking-tight">Privacy</h1>
      <p className="mt-2 text-muted">How LumiLattice handles your data. Updated November 1, 2026.</p>

      <h2 className={heading}>Google sign-in (private mode only)</h2>
      <p className="mt-1">
        We ask Google only for your account&apos;s permanent ID and your name. We do not ask for your email address or
        your password, and we do not keep the access token that Google gives us. From your name, we make a short tag,
        such as C. Jung, and we do not keep the full name. We use the ID to mark candidates as yours. A signed cookie
        keeps you signed in for up to 7 days.
      </p>
      <p className="mt-1">
        We show your tag only if you publish a candidate with it. If you choose anonymous credit, other users do not
        see your account, but the ID stays in our database.
      </p>

      <h2 className={heading}>What you save</h2>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        <li>In public mode, anyone can read the candidates, decisions, reasons, and measurements that you save.</li>
        <li>In private mode, other users cannot see them until you publish them. The operator can read the database.</li>
        <li>What you publish is available to everyone under CC BY 4.0. Undoing it cannot recover copies made by others.</li>
      </ul>

      <h2 className={heading}>What goes to other services</h2>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        <li>What you ask the agent, and the candidate data for a critique, go to the Meta Model API.</li>
        <li>Novelty checks and searches send formulas to Materials Project, COD, OpenAlex, Crossref, arXiv, and Semantic Scholar.</li>
        <li>The site runs on Vercel, and the backend and database run on Railway. These hosts can keep their own technical logs.</li>
      </ul>
      <p className="mt-1">Do not enter confidential work in either mode.</p>

      <h2 className={heading}>What we do not keep</h2>
      <p className="mt-1">
        The app does not store your IP address. The request limit keeps only a keyed hash of it, for about 10 minutes. The
        researcher globe keeps only a count for each country.
      </p>

      <h2 className={heading}>Removing your data</h2>
      <p className="mt-1">
        The app has no self-service delete function. To ask for removal, open an issue in the{" "}
        <a className="text-accent-text underline" href={`${REPOSITORY}/issues`}>
          project repository
        </a>
        . Do not put personal details in the issue.
      </p>
    </main>
  );
}
