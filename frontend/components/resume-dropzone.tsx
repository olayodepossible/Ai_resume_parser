"use client";

import { useId, useRef, useState } from "react";

import {
  ACCEPTED_EXTENSION,
  ACCEPTED_MIME,
  MAX_FILE_SIZE_MB,
  MAX_RESUME_FILES,
  formatBytes,
  rejectionReason,
} from "@/lib/limits";

import { Alert } from "./alert";
import { CloseIcon, FileTextIcon, UploadIcon } from "./icons";

export interface LocalRejection {
  filename: string;
  reason: string;
}

/**
 * Multi-file PDF picker with drag-and-drop.
 *
 * Files accumulate across drops and picks rather than replacing the
 * selection, because a recruiter working from several folders will add them in
 * batches. `key(file)` dedupes so the same resume dropped twice is not sent
 * (and scored) twice.
 */
export function ResumeDropzone({
  files,
  onChange,
  disabled = false,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const [dragging, setDragging] = useState(false);
  const [rejections, setRejections] = useState<LocalRejection[]>([]);
  const [overflow, setOverflow] = useState<number>(0);

  function add(incoming: FileList | null) {
    if (!incoming || disabled) return;

    const existing = new Set(files.map(key));
    const nextRejections: LocalRejection[] = [];
    const accepted: File[] = [];

    for (const file of Array.from(incoming)) {
      const reason = rejectionReason(file);

      if (reason) {
        nextRejections.push({ filename: file.name, reason });
        continue;
      }

      if (existing.has(key(file))) continue;

      existing.add(key(file));
      accepted.push(file);
    }

    const room = MAX_RESUME_FILES - files.length;
    const admitted = accepted.slice(0, Math.max(0, room));

    setRejections(nextRejections);
    setOverflow(accepted.length - admitted.length);

    if (admitted.length) onChange([...files, ...admitted]);
  }

  function remove(target: File) {
    onChange(files.filter((file) => key(file) !== key(target)));
  }

  const full = files.length >= MAX_RESUME_FILES;

  return (
    <div>
      {/* The label is the drop target, so a click anywhere in it opens the
          file picker without a nested-button/keyboard-trap workaround. */}
      <label
        htmlFor={inputId}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !full) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          add(event.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragging
            ? "border-brand bg-brand-soft"
            : "border-line-strong hover:border-brand hover:bg-bg-accent"
        } ${disabled || full ? "pointer-events-none opacity-60" : ""}`}
      >
        <span className="inline-flex size-10 items-center justify-center rounded-full bg-brand-soft text-brand">
          <UploadIcon size={19} />
        </span>

        <span className="mt-3 text-[13px] font-medium">
          {full
            ? `Maximum of ${MAX_RESUME_FILES} resumes reached`
            : "Drop resume PDFs here, or click to browse"}
        </span>

        <span className="mt-1 text-xs text-faint">
          PDF only · up to {MAX_FILE_SIZE_MB} MB each · {MAX_RESUME_FILES} per
          batch
        </span>
      </label>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={`${ACCEPTED_MIME},${ACCEPTED_EXTENSION}`}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          add(event.target.files);
          // Reset so re-picking the same file after removing it still fires.
          event.target.value = "";
        }}
      />

      {rejections.length || overflow ? (
        <div className="mt-3 space-y-2">
          {rejections.length ? (
            <Alert
              tone="warning"
              title={`${rejections.length} file${rejections.length === 1 ? "" : "s"} skipped`}
            >
              <ul className="mt-1 space-y-0.5">
                {rejections.map((item) => (
                  <li key={item.filename}>
                    <span className="font-medium">{item.filename}</span> —{" "}
                    {item.reason}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}

          {overflow ? (
            <Alert tone="warning">
              {overflow} more file{overflow === 1 ? " was" : "s were"} left out:
              a batch holds {MAX_RESUME_FILES} resumes.
            </Alert>
          ) : null}
        </div>
      ) : null}

      {files.length ? (
        <div className="mt-4">
          <div className="flex items-center justify-between">
            <p className="text-[13px] font-medium">
              {files.length} resume{files.length === 1 ? "" : "s"} ready
            </p>
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                onChange([]);
                setRejections([]);
                setOverflow(0);
              }}
              className="btn btn-sm btn-ghost"
            >
              Clear all
            </button>
          </div>

          <ul className="mt-2 max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {files.map((file) => (
              <li
                key={key(file)}
                className="flex items-center gap-2.5 rounded-lg border border-line bg-panel px-3 py-2"
              >
                <FileTextIcon size={15} className="shrink-0 text-faint" />
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  {file.name}
                </span>
                <span className="shrink-0 text-xs tabular-nums text-faint">
                  {formatBytes(file.size)}
                </span>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => remove(file)}
                  aria-label={`Remove ${file.name}`}
                  className="btn btn-ghost size-6 shrink-0 p-0"
                >
                  <CloseIcon size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function key(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}
