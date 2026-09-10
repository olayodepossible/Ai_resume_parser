"use client";

import { useId, useState } from "react";

import {
  ACCEPTED_EXTENSION,
  ACCEPTED_MIME,
  MAX_FILE_SIZE_MB,
  MAX_JOB_DESCRIPTION_CHARS,
  formatBytes,
  rejectionReason,
} from "@/lib/limits";

import { Alert } from "./alert";
import { CloseIcon, FileTextIcon, UploadIcon } from "./icons";

export type JobDescriptionMode = "text" | "file";

/**
 * Paste-or-upload job description input.
 *
 * The two modes are exclusive by construction: `POST /screenings` returns 422
 * if both `job_description_text` and `job_description_file` are sent, so this
 * is tabs rather than two always-visible fields.
 */
export function JobDescriptionInput({
  mode,
  onModeChange,
  text,
  onTextChange,
  file,
  onFileChange,
  disabled = false,
}: {
  mode: JobDescriptionMode;
  onModeChange: (mode: JobDescriptionMode) => void;
  text: string;
  onTextChange: (text: string) => void;
  file: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
}) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);
  const [rejection, setRejection] = useState<string | null>(null);

  function accept(incoming: FileList | null) {
    if (!incoming?.length || disabled) return;

    const candidate = incoming[0];
    const reason = rejectionReason(candidate);

    setRejection(reason);
    onFileChange(reason ? null : candidate);
  }

  const overLimit = text.length > MAX_JOB_DESCRIPTION_CHARS;

  return (
    <div>
      <div
        role="tablist"
        aria-label="Job description source"
        className="inline-flex rounded-lg border border-line bg-bg-accent p-0.5"
      >
        {(
          [
            ["text", "Paste text"],
            ["file", "Upload PDF"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            disabled={disabled}
            onClick={() => onModeChange(value)}
            className={`btn btn-sm ${
              mode === value
                ? "bg-panel text-text shadow-sm"
                : "text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "text" ? (
        <div className="mt-3">
          <textarea
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            disabled={disabled}
            rows={9}
            className="field resize-y font-normal"
            placeholder={
              "Paste the role's responsibilities and requirements.\n\nThe more concrete the must-haves, the sharper the scoring."
            }
          />

          <div className="mt-1.5 flex items-center justify-between text-xs">
            <span className="text-faint">
              {overLimit
                ? `Only the first ${MAX_JOB_DESCRIPTION_CHARS.toLocaleString()} characters are used.`
                : "Plain text — formatting is ignored."}
            </span>
            <span
              className={`tabular-nums ${overLimit ? "text-caution" : "text-faint"}`}
            >
              {text.length.toLocaleString()} /{" "}
              {MAX_JOB_DESCRIPTION_CHARS.toLocaleString()}
            </span>
          </div>
        </div>
      ) : (
        <div className="mt-3">
          {file ? (
            <div className="flex items-center gap-2.5 rounded-lg border border-line bg-panel px-3 py-2.5">
              <FileTextIcon size={16} className="shrink-0 text-brand" />
              <span className="min-w-0 flex-1 truncate text-[13px]">
                {file.name}
              </span>
              <span className="shrink-0 text-xs tabular-nums text-faint">
                {formatBytes(file.size)}
              </span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onFileChange(null)}
                aria-label="Remove job description file"
                className="btn btn-ghost size-6 shrink-0 p-0"
              >
                <CloseIcon size={14} />
              </button>
            </div>
          ) : (
            <label
              htmlFor={inputId}
              onDragOver={(event) => {
                event.preventDefault();
                if (!disabled) setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                accept(event.dataTransfer.files);
              }}
              className={`flex cursor-pointer items-center justify-center gap-2.5 rounded-xl border-2 border-dashed px-5 py-7 text-center transition-colors ${
                dragging
                  ? "border-brand bg-brand-soft"
                  : "border-line-strong hover:border-brand hover:bg-bg-accent"
              } ${disabled ? "pointer-events-none opacity-60" : ""}`}
            >
              <UploadIcon size={17} className="text-brand" />
              <span className="text-[13px] font-medium">
                Drop the job description PDF, or click to browse
              </span>
            </label>
          )}

          <input
            id={inputId}
            type="file"
            accept={`${ACCEPTED_MIME},${ACCEPTED_EXTENSION}`}
            disabled={disabled}
            className="sr-only"
            onChange={(event) => {
              accept(event.target.files);
              event.target.value = "";
            }}
          />

          {rejection ? (
            <div className="mt-2.5">
              <Alert tone="warning">
                {rejection}. Job descriptions must be a PDF under{" "}
                {MAX_FILE_SIZE_MB} MB — paste the text instead if you only have
                a Word file.
              </Alert>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
