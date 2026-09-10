/**
 * Mirrors `backend/app/schemas.py`. Field names are camelCase on both sides,
 * so responses are used as-is with no mapping layer.
 */

export type Theme = "light" | "dark" | "system";

export interface UserSettings {
  company: string;
  defaultPositionTitle: string;
  emailOnCompletion: boolean;
  theme: Theme;
}

export interface User {
  id: string;
  email: string;
  fullName: string;
  createdAt: string;
  settings: UserSettings;
}

export interface AuthResponse {
  accessToken: string;
  tokenType: "bearer";
  /** Epoch seconds, UTC. */
  expiresAt: number;
  user: User;
}

export interface CandidateSummary {
  candidateId: string;
  name: string;
  email: string;
  sourceFilename: string;
  resumeChars: number;
}

export interface RejectedFile {
  filename: string;
  reason: string;
}

/**
 * The model is prompted for these values but they arrive as free-form strings;
 * `normalizeRecommendation` in `lib/screening.ts` maps them onto a fixed set.
 */
export interface ScreeningResult {
  candidateId: string;
  score: number;
  recommendation: string;
  keySkills: string[];
  concerns: string[];
  summary: string;
}

export interface RankedCandidate {
  candidateId: string;
  rank: number;
  finalScore: number;
  justification: string;
}

export interface RankingOutput {
  rankedCandidates: RankedCandidate[];
  topRecommendation: string;
}

export interface ScreeningResponse {
  positionTitle: string;
  jobDescriptionChars: number;
  totalUploaded: number;
  totalEvaluated: number;
  candidates: CandidateSummary[];
  rejectedFiles: RejectedFile[];
  screeningResults: ScreeningResult[];
  rankingOutput: RankingOutput;
  processedAt: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  model: string;
  llmConfigured: boolean;
}
