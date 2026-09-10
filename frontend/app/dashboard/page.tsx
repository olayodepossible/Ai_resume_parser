"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/components/alert";
import { LayersIcon, SparklesIcon } from "@/components/icons";
import { ResultsView } from "@/components/results-view";
import { ScreeningPane } from "@/components/screening-pane";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { HealthResponse, ScreeningResponse } from "@/lib/types";

export default function DashboardPage() {
  const { user } = useAuth();

  const [paneOpen, setPaneOpen] = useState(false);
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Surfaced up front because a missing OPENROUTER_API_KEY only fails at the
  // end of a batch otherwise — after the user has picked every file.
  useEffect(() => {
    let active = true;

    api
      .health()
      .then((fetched) => {
        if (active) setHealth(fetched);
      })
      .catch(() => {
        if (active) setHealth(null);
      });

    return () => {
      active = false;
    };
  }, []);

  const firstName = (user?.fullName || "").trim().split(/\s+/)[0];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {firstName ? `Welcome back, ${firstName}` : "Dashboard"}
          </h1>
          <p className="mt-1.5 text-[13px] text-muted">
            {result
              ? "Your latest shortlist is below. Run another batch any time."
              : "Upload a batch of resumes and a job description to get a ranked shortlist."}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setPaneOpen(true)}
          className="btn btn-md btn-primary"
        >
          <SparklesIcon size={16} />
          Screen candidates
        </button>
      </div>

      {health && !health.llmConfigured ? (
        <div className="mt-6">
          <Alert tone="warning" title="The model provider is not configured">
            <p>
              The backend has no <code>OPENROUTER_API_KEY</code> set, so
              screening requests will fail with a 503. Add it to{" "}
              <code>backend/.env</code> and restart the API.
            </p>
          </Alert>
        </div>
      ) : null}

      <div className="mt-7">
        {result ? (
          <ResultsView result={result} />
        ) : (
          <EmptyState onStart={() => setPaneOpen(true)} />
        )}
      </div>

      <ScreeningPane
        open={paneOpen}
        onClose={() => setPaneOpen(false)}
        onComplete={setResult}
      />
    </>
  );
}

function EmptyState({ onStart }: { onStart: () => void }) {
  return (
    <div className="card flex flex-col items-center px-6 py-16 text-center">
      <span className="inline-flex size-12 items-center justify-center rounded-xl bg-brand-soft text-brand">
        <LayersIcon size={22} />
      </span>

      <h2 className="mt-4 text-[15px] font-semibold">No screenings yet</h2>
      <p className="mt-2 max-w-md text-[13px] leading-relaxed text-muted">
        Results are held for this session only — nothing is stored server-side,
        so export or note down anything you want to keep before you sign out.
      </p>

      <button type="button" onClick={onStart} className="btn btn-md btn-primary mt-6">
        <SparklesIcon size={16} />
        Screen candidates
      </button>
    </div>
  );
}
