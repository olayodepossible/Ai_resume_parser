/**
 * Client-side mirrors of the upload limits in `backend/app/config.py`.
 *
 * Checking them here turns a 413/422 round-trip into an inline message; the
 * backend still enforces them, so a mismatch costs a worse error, not a
 * bypassed limit. Keep in step with `MAX_RESUME_FILES` / `MAX_FILE_SIZE_MB`.
 */

export const MAX_RESUME_FILES = 25;
export const MAX_FILE_SIZE_MB = 10;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
export const MAX_JOB_DESCRIPTION_CHARS = 20_000;

export const ACCEPTED_MIME = "application/pdf";
export const ACCEPTED_EXTENSION = ".pdf";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Returns a reason the file is unusable, or `null` when it is fine. */
export function rejectionReason(file: File): string | null {
  const looksLikePdf =
    file.type === ACCEPTED_MIME ||
    file.name.toLowerCase().endsWith(ACCEPTED_EXTENSION);

  if (!looksLikePdf) return "Not a PDF";
  if (file.size === 0) return "File is empty";
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `Larger than ${MAX_FILE_SIZE_MB} MB`;
  }

  return null;
}
