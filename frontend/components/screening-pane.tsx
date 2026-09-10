"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { MAX_RESUME_FILES } from "@/lib/limits";
import type { ScreeningResponse } from "@/lib/types";

import { Alert } from "./alert";
import { CloseIcon, SparklesIcon, SpinnerIcon } from "./icons";
import {
  JobDescriptionInput,
  type JobDescriptionMode,
} from "./job-description-input";
import { ResumeDropzone } from "./resume-dropzone";

/**
 * The slide-over that collects a batch and posts it to `/api/v1/screenings`.
 *
 * Screening a full batch is a long request — the backend screens four resumes
 * at a time and then makes a ranking call — so the pane stays open with a
 * progress state and an explicit cancel rather than closing optimistically.
 */
export function ScreeningPane({
  open,
  onClose,
  onComplete,
}: {
  open: boolean;
  onClose: () => void;
  onComplete: (result: ScreeningResponse) => void;
}) {
  const { token, user } = useAuth();

  const [resumes, setResumes] = useState<File[]>([]);
  const [mode, setMode] = useState<JobDescriptionMode>("text");
  const [jobText, setJobText] = useState("");
  const [jobFile, setJobFile] = useState<File | null>(null);
  const [positionTitle, setPositionTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Prefill the title from the user's settings when the pane opens, without
  // clobbering a title they have already typed this session.
  useEffect(() => {
    if (!open) return;

    setPositionTitle((current) =>
      current ? current : (user?.settings.defaultPositionTitle ?? ""),
    );
  }, [open, user]);

  // Move focus into the pane once per opening. Kept separate from the
  // listener effect below: that one re-runs whenever `submitting` or the
  // parent's `onClose` identity changes, which must not yank focus out of
  // whatever field the user is filling in.
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  // Escape closes the pane, and the page behind it should not scroll while it
  // is open. Escape is ignored mid-request so a batch in flight is not
  // abandoned by a stray keypress.
  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !submitting) onClose();
    }

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, submitting, onClose]);

  // Abandon an in-flight request if the pane unmounts, so its response cannot
  // land on a screen the user has navigated away from.
  useEffect(() => () => abortRef.current?.abort(), []);

  const hasJobDescription =
    mode === "text" ? jobText.trim().length > 0 : jobFile !== null;
  const ready = resumes.length > 0 && hasJobDescription;

  function reset() {
    setResumes([]);
    setJobText("");
    setJobFile(null);
    setPositionTitle("");
    setError(null);
    setMode("text");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!ready || submitting) return;

    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);
    setSubmitting(true);

    try {
      const result = await api.createScreening(
        {
          resumes,
          // Only the active tab's value is sent; sending both is a 422.
          jobDescriptionText: mode === "text" ? jobText : undefined,
          jobDescriptionFile: mode === "file" ? jobFile : null,
          positionTitle,
        },
        { token, signal: controller.signal },
      );

      onComplete(result);
      reset();
      onClose();
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        return;
      }

      setError(
        caught instanceof ApiError
          ? caught.message
          : "The screening could not be completed.",
      );
    } finally {
      setSubmitting(false);
      abortRef.current = null;
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close screening panel"
        disabled={submitting}
        onClick={onClose}
        className="absolute inset-0 bg-black/45 backdrop-blur-[2px] disabled:cursor-wait"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="screening-pane-title"
        tabIndex={-1}
        className="relative flex h-full w-full max-w-xl flex-col border-l border-line bg-panel shadow-panel outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <h2
              id="screening-pane-title"
              className="text-[17px] font-semibold tracking-tight"
            >
              Screen candidates
            </h2>
            <p className="mt-1 text-[13px] text-muted">
              Add the resumes and the role they applied for.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="btn btn-ghost size-9 shrink-0 p-0"
          >
            <CloseIcon size={18} />
          </button>
        </header>

        <form
          onSubmit={handleSubmit}
          className="flex min-h-0 flex-1 flex-col"
          noValidate
        >
          <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-6 py-6">
            <Step
              index={1}
              title="Resumes"
              hint={`PDF · up to ${MAX_RESUME_FILES}`}
            >
              <ResumeDropzone
                files={resumes}
                onChange={setResumes}
                disabled={submitting}
              />
            </Step>

            <Step index={2} title="Job description">
              <JobDescriptionInput
                mode={mode}
                onModeChange={setMode}
                text={jobText}
                onTextChange={setJobText}
                file={jobFile}
                onFileChange={setJobFile}
                disabled={submitting}
              />
            </Step>

            <Step index={3} title="Position title" hint="Optional">
              <input
                type="text"
                value={positionTitle}
                onChange={(event) => setPositionTitle(event.target.value)}
                disabled={submitting}
                className="field"
                placeholder={
                  mode === "file"
                    ? "Defaults to the PDF's filename"
                    : "e.g. Senior ML Engineer"
                }
              />
              <p className="mt-1.5 text-xs text-faint">
                Shown on the results and given to the model as the role being
                filled.
              </p>
            </Step>

            {error ? <Alert title="Screening failed">{error}</Alert> : null}
          </div>

          <footer className="border-t border-line bg-panel px-6 py-4">
            {submitting ? (
              <p className="mb-3 flex items-center gap-2 text-[13px] text-muted">
                <SpinnerIcon size={15} className="text-brand" />
                Screening {resumes.length} resume
                {resumes.length === 1 ? "" : "s"} and ranking the batch — this
                takes a moment per candidate.
              </p>
            ) : null}

            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-faint">
                {resumes.length
                  ? `${resumes.length} resume${resumes.length === 1 ? "" : "s"} selected`
                  : "No resumes selected yet"}
              </p>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={submitting ? () => abortRef.current?.abort() : onClose}
                  className="btn btn-md btn-secondary"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={!ready || submitting}
                  className="btn btn-md btn-primary"
                >
                  {submitting ? (
                    <SpinnerIcon size={16} />
                  ) : (
                    <SparklesIcon size={16} />
                  )}
                  {submitting ? "Screening…" : "Send for screening"}
                </button>
              </div>
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
}

function Step({
  index,
  title,
  hint,
  children,
}: {
  index: number;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2.5 flex items-center gap-2.5">
        <span className="inline-flex size-6 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand">
          {index}
        </span>
        <h3 className="text-[14px] font-semibold">{title}</h3>
        {hint ? <span className="text-xs text-faint">{hint}</span> : null}
      </div>

      {children}
    </section>
  );
}
