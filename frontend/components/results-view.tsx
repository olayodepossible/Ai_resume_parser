"use client";

import { useState } from "react";

import {
  VERDICT_LABEL,
  VERDICT_STYLE,
  formatProcessedAt,
  toCandidateRows,
  type CandidateRow,
} from "@/lib/screening";
import type { ScreeningResponse } from "@/lib/types";

import { Alert } from "./alert";
import { Avatar } from "./avatar";
import { ChevronDownIcon, FileTextIcon, TrophyIcon } from "./icons";

export function ResultsView({ result }: { result: ScreeningResponse }) {
  const rows = toCandidateRows(result);

  return (
    <div className="space-y-5">
      <div className="card p-5 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              {result.positionTitle}
            </h2>
            <p className="mt-1 text-[13px] text-muted">
              Screened {formatProcessedAt(result.processedAt)}
            </p>
          </div>

          <dl className="flex gap-6">
            <Stat label="Uploaded" value={result.totalUploaded} />
            <Stat label="Evaluated" value={result.totalEvaluated} />
            <Stat
              label="Skipped"
              value={result.rejectedFiles.length}
              tone={result.rejectedFiles.length ? "caution" : undefined}
            />
          </dl>
        </div>

        {result.rankingOutput.topRecommendation ? (
          <div className="mt-5 flex gap-3 rounded-lg border border-brand/25 bg-brand-soft p-4">
            <TrophyIcon size={17} className="mt-0.5 shrink-0 text-brand" />
            <div>
              <p className="text-[13px] font-semibold">Top recommendation</p>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">
                {result.rankingOutput.topRecommendation}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {result.rejectedFiles.length ? (
        <Alert
          tone="warning"
          title={`${result.rejectedFiles.length} file${
            result.rejectedFiles.length === 1 ? "" : "s"
          } could not be read`}
        >
          <ul className="mt-1 space-y-0.5">
            {result.rejectedFiles.map((item) => (
              <li key={item.filename}>
                <span className="font-medium">{item.filename}</span> —{" "}
                {item.reason}
              </li>
            ))}
          </ul>
          <p className="mt-2 opacity-90">
            Scanned resumes have no text layer to read; the rest of the batch
            was screened as normal.
          </p>
        </Alert>
      ) : null}

      <ol className="space-y-3">
        {rows.map((row) => (
          <CandidateCard key={row.candidateId} row={row} />
        ))}
      </ol>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "caution";
}) {
  return (
    <div>
      <dt className="text-xs text-faint">{label}</dt>
      <dd
        className={`mt-0.5 text-xl font-semibold tabular-nums ${
          tone === "caution" ? "text-caution" : ""
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

function CandidateCard({ row }: { row: CandidateRow }) {
  const [expanded, setExpanded] = useState(false);
  const score = row.finalScore ?? row.screeningScore;

  return (
    <li className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors hover:bg-bg-accent"
      >
        <span className="w-6 shrink-0 text-center text-[13px] font-semibold tabular-nums text-faint">
          {row.rank ?? "—"}
        </span>

        <Avatar name={row.name} size={36} />

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-semibold">
            {row.name}
          </span>
          <span className="block truncate text-xs text-muted">
            {row.email || row.sourceFilename}
          </span>
        </span>

        <span className="hidden w-40 shrink-0 sm:block">
          <ScoreBar score={score} />
        </span>

        <span
          className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium ${VERDICT_STYLE[row.verdict]}`}
        >
          {VERDICT_LABEL[row.verdict]}
        </span>

        <ChevronDownIcon
          size={16}
          className={`shrink-0 text-faint transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {expanded ? (
        <div className="space-y-4 border-t border-line px-4 py-4 sm:pl-[4.5rem]">
          <div className="sm:hidden">
            <ScoreBar score={score} />
          </div>

          {row.summary ? (
            <Section title="Screening summary">
              <p className="text-[13px] leading-relaxed text-muted">
                {row.summary}
              </p>
            </Section>
          ) : null}

          {row.justification ? (
            <Section title={`Why rank ${row.rank ?? "—"}`}>
              <p className="text-[13px] leading-relaxed text-muted">
                {row.justification}
              </p>
            </Section>
          ) : null}

          {row.keySkills.length ? (
            <Section title="Matched skills">
              <ul className="flex flex-wrap gap-1.5">
                {row.keySkills.map((skill) => (
                  <li
                    key={skill}
                    className="rounded-md border border-line bg-bg-accent px-2 py-0.5 text-xs"
                  >
                    {skill}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {row.concerns.length ? (
            <Section title="Concerns">
              <ul className="space-y-1 text-[13px] text-muted">
                {row.concerns.map((concern) => (
                  <li key={concern} className="flex gap-2">
                    <span className="text-caution">•</span>
                    <span>{concern}</span>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          <p className="flex items-center gap-1.5 text-xs text-faint">
            <FileTextIcon size={13} />
            {row.sourceFilename || "source file unknown"}
            {row.screeningScore !== null && row.finalScore !== null &&
            row.screeningScore !== row.finalScore ? (
              <span>
                · screening {Math.round(row.screeningScore)} · ranked{" "}
                {Math.round(row.finalScore)}
              </span>
            ) : null}
          </p>
        </div>
      ) : null}
    </li>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold tracking-wide text-faint uppercase">
        {title}
      </h4>
      {children}
    </div>
  );
}

function ScoreBar({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="text-xs text-faint">No score</span>;
  }

  // The model is asked for 0-100 but is not guaranteed to stay inside it.
  const clamped = Math.max(0, Math.min(100, score));

  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-accent">
        <span
          className="block h-full rounded-full bg-brand"
          style={{ width: `${clamped}%` }}
        />
      </span>
      <span className="w-7 shrink-0 text-right text-[13px] font-medium tabular-nums">
        {Math.round(score)}
      </span>
    </span>
  );
}
