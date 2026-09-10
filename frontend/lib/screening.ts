import type {
  CandidateSummary,
  RankedCandidate,
  ScreeningResponse,
  ScreeningResult,
} from "./types";

export type Verdict = "strong_yes" | "yes" | "maybe" | "no" | "unknown";

/**
 * The model is asked for one of the four verdicts but is not constrained to
 * them, so anything unrecognised lands on "unknown" rather than being shown
 * to the user raw.
 */
export function normalizeVerdict(recommendation: string): Verdict {
  const value = recommendation.trim().toLowerCase().replace(/[\s-]+/g, "_");

  if (value === "strong_yes" || value === "strongyes") return "strong_yes";
  if (value === "yes") return "yes";
  if (value === "maybe") return "maybe";
  if (value === "no" || value === "strong_no") return "no";

  return "unknown";
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  strong_yes: "Strong yes",
  yes: "Yes",
  maybe: "Maybe",
  no: "No",
  unknown: "Unscored",
};

/** Tailwind classes per verdict, so the badge and the score bar agree. */
export const VERDICT_STYLE: Record<Verdict, string> = {
  strong_yes: "bg-positive/12 text-positive border-positive/30",
  yes: "bg-positive/10 text-positive border-positive/25",
  maybe: "bg-caution/12 text-caution border-caution/30",
  no: "bg-negative/10 text-negative border-negative/25",
  unknown: "bg-faint/10 text-faint border-line-strong",
};

export interface CandidateRow {
  candidateId: string;
  rank: number | null;
  name: string;
  email: string;
  sourceFilename: string;
  finalScore: number | null;
  screeningScore: number | null;
  verdict: Verdict;
  keySkills: string[];
  concerns: string[];
  summary: string;
  justification: string;
}

/**
 * Joins the three per-candidate arrays in a `ScreeningResponse` on
 * `candidateId` and returns them in ranking order.
 *
 * The backend assembles the arrays independently, and a candidate the model
 * omitted from the ranking still has a screening result, so this joins on
 * lookups instead of assuming the arrays line up by index.
 */
export function toCandidateRows(response: ScreeningResponse): CandidateRow[] {
  const summaries = new Map<string, CandidateSummary>(
    response.candidates.map((item) => [item.candidateId, item]),
  );
  const screenings = new Map<string, ScreeningResult>(
    response.screeningResults.map((item) => [item.candidateId, item]),
  );
  const rankings = new Map<string, RankedCandidate>(
    response.rankingOutput.rankedCandidates.map((item) => [
      item.candidateId,
      item,
    ]),
  );

  const ids = [
    ...new Set([
      ...response.rankingOutput.rankedCandidates.map((item) => item.candidateId),
      ...response.candidates.map((item) => item.candidateId),
    ]),
  ];

  const rows = ids.map((candidateId) => {
    const summary = summaries.get(candidateId);
    const screening = screenings.get(candidateId);
    const ranking = rankings.get(candidateId);

    return {
      candidateId,
      rank: ranking?.rank ?? null,
      name: summary?.name ?? candidateId,
      email: summary?.email ?? "",
      sourceFilename: summary?.sourceFilename ?? "",
      finalScore: ranking?.finalScore ?? null,
      screeningScore: screening?.score ?? null,
      verdict: normalizeVerdict(screening?.recommendation ?? ""),
      keySkills: screening?.keySkills ?? [],
      concerns: screening?.concerns ?? [],
      summary: screening?.summary ?? "",
      justification: ranking?.justification ?? "",
    } satisfies CandidateRow;
  });

  // Ranked candidates first, in rank order; unranked ones keep upload order
  // at the bottom.
  return rows.sort((a, b) => {
    if (a.rank !== null && b.rank !== null) return a.rank - b.rank;
    if (a.rank !== null) return -1;
    if (b.rank !== null) return 1;

    return 0;
  });
}

export function formatProcessedAt(value: string): string {
  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) return value;

  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);

  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();

  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}
