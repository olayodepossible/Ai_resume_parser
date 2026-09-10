import Link from "next/link";

import {
  ArrowRightIcon,
  FileTextIcon,
  LayersIcon,
  LogoMark,
  ShieldIcon,
  SparklesIcon,
  TrophyIcon,
} from "@/components/icons";

const FEATURES = [
  {
    icon: LayersIcon,
    title: "Screen the whole pile at once",
    body: "Drop in up to 25 resume PDFs and one job description. Every candidate is read and scored in the same pass, so the comparison is apples to apples.",
  },
  {
    icon: TrophyIcon,
    title: "A ranked shortlist, with reasons",
    body: "Each candidate comes back with a score, matched skills, concerns, and a written justification for where they landed — not just a number.",
  },
  {
    icon: ShieldIcon,
    title: "Nothing is stored",
    body: "Resumes are parsed in memory to produce the screening and are not kept afterwards. An unreadable file is reported, not silently dropped.",
  },
];

const STEPS = [
  {
    title: "Upload the resumes",
    body: "As many PDFs as you have. Files that cannot be read are flagged individually.",
  },
  {
    title: "Add the job description",
    body: "Paste the text or upload it as a PDF — whichever you already have to hand.",
  },
  {
    title: "Read the shortlist",
    body: "A ranked table with per-candidate scores, strengths, and concerns.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <LogoMark size={28} className="text-brand" />
            <span className="text-[15px] font-semibold tracking-tight">
              Shortlist
            </span>
          </Link>

          <nav className="flex items-center gap-2">
            <Link href="/login" className="btn btn-sm btn-ghost">
              Sign in
            </Link>
            <Link href="/signup" className="btn btn-sm btn-primary">
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden">
          {/* Decorative wash behind the hero. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 -top-40 h-[420px] opacity-70"
            style={{
              background:
                "radial-gradient(60% 100% at 50% 0%, var(--brand-soft), transparent 70%)",
            }}
          />

          <div className="relative mx-auto max-w-6xl px-6 pt-20 pb-16 text-center">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-3 py-1 text-xs font-medium text-muted">
              <SparklesIcon size={13} className="text-brand" />
              LLM-assisted screening
            </span>

            <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Turn a stack of resumes into a ranked shortlist
            </h1>

            <p className="mx-auto mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
              Upload the resumes and the job description. Every candidate is
              scored against the same requirements and returned with matched
              skills, concerns, and a ranking you can defend in a hiring
              meeting.
            </p>

            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <Link href="/signup" className="btn btn-md btn-primary">
                Screen your first batch
                <ArrowRightIcon size={16} />
              </Link>
              <Link href="/login" className="btn btn-md btn-secondary">
                I already have an account
              </Link>
            </div>

            <PreviewCard />
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="card p-6 shadow-panel">
                <span className="inline-flex size-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <Icon size={19} />
                </span>
                <h2 className="mt-4 text-[15px] font-semibold">{title}</h2>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  {body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-y border-line bg-bg-accent">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-center text-2xl font-semibold tracking-tight">
              Three steps, one pass
            </h2>

            <ol className="mt-10 grid gap-8 sm:grid-cols-3">
              {STEPS.map((step, index) => (
                <li key={step.title} className="relative">
                  <span className="inline-flex size-8 items-center justify-center rounded-full bg-brand text-[13px] font-semibold text-brand-on">
                    {index + 1}
                  </span>
                  <h3 className="mt-3.5 text-[15px] font-semibold">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
                    {step.body}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h2 className="text-2xl font-semibold tracking-tight">
            Ready when your inbox is
          </h2>
          <p className="mt-3 text-[15px] text-muted">
            Create an account and screen a batch in the next few minutes.
          </p>
          <Link href="/signup" className="btn btn-md btn-primary mt-7">
            Create an account
            <ArrowRightIcon size={16} />
          </Link>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 text-[13px] text-faint sm:flex-row">
          <div className="flex items-center gap-2">
            <LogoMark size={18} className="text-brand" />
            <span>Shortlist</span>
          </div>
          <p>Screening assists the decision; a human still makes it. &copy; {new Date().getFullYear()}</p>
        </div>
      </footer>
      
    </div>
  );
}

/** A static mock of the results table, purely illustrative. */
function PreviewCard() {
  const rows = [
    { rank: 1, name: "A. Johnson", score: 91, verdict: "Strong yes" },
    { rank: 2, name: "R. Mehta", score: 78, verdict: "Yes" },
    { rank: 3, name: "B. Martinez", score: 64, verdict: "Maybe" },
  ];

  return (
    <div className="mx-auto mt-16 max-w-3xl">
      <div className="card overflow-hidden text-left shadow-panel">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <FileTextIcon size={15} className="text-faint" />
          <span className="text-[13px] font-medium">
            Senior ML Engineer — 3 candidates
          </span>
        </div>

        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-xs text-faint">
              <th className="px-4 py-2 font-medium">#</th>
              <th className="px-4 py-2 font-medium">Candidate</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.rank} className="border-t border-line">
                <td className="px-4 py-3 text-faint">{row.rank}</td>
                <td className="px-4 py-3 font-medium">{row.name}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-24 overflow-hidden rounded-full bg-bg-accent">
                      <span
                        className="block h-full rounded-full bg-brand"
                        style={{ width: `${row.score}%` }}
                      />
                    </span>
                    <span className="tabular-nums text-muted">{row.score}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted">{row.verdict}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
