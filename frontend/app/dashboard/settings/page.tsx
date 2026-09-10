"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/alert";
import { Avatar } from "@/components/avatar";
import { CheckIcon, SpinnerIcon } from "@/components/icons";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Theme, UserSettings } from "@/lib/types";

const THEMES: { value: Theme; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export default function SettingsPage() {
  const { user, updateProfile } = useAuth();

  const [fullName, setFullName] = useState("");
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  // Seed the form from the user record once it is available, and re-seed if it
  // changes underneath us (a save elsewhere, or a token refresh).
  useEffect(() => {
    if (!user) return;

    setFullName(user.fullName);
    setSettings(user.settings);
  }, [user]);

  if (!user || !settings) return null;

  function patch<K extends keyof UserSettings>(key: K, value: UserSettings[K]) {
    setSettings((current) => (current ? { ...current, [key]: value } : current));
    setStatus("idle");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!settings) return;

    setError(null);
    setStatus("saving");

    try {
      await updateProfile({ fullName, settings });
      setStatus("saved");
    } catch (caught) {
      setStatus("idle");
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Your changes could not be saved.",
      );
    }
  }

  const dirty =
    fullName !== user.fullName ||
    JSON.stringify(settings) !== JSON.stringify(user.settings);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-1.5 text-[13px] text-muted">
            Your profile and screening defaults.
          </p>
        </div>

        <Link href="/dashboard" className="btn btn-sm btn-secondary">
          Back to dashboard
        </Link>
      </div>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        {error ? <Alert>{error}</Alert> : null}

        <section className="card p-5">
          <h2 className="text-[15px] font-semibold">Profile</h2>

          <div className="mt-4 flex items-center gap-4">
            <Avatar name={fullName || user.email} size={52} />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium">{user.email}</p>
              <p className="mt-0.5 text-xs text-faint">
                Member since {new Date(user.createdAt).toLocaleDateString()}
              </p>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            <div>
              <label htmlFor="fullName" className="label">
                Full name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(event) => {
                  setFullName(event.target.value);
                  setStatus("idle");
                }}
                className="field"
                placeholder="Ada Lovelace"
              />
            </div>

            <div>
              <label htmlFor="email" className="label">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={user.email}
                disabled
                className="field"
              />
              <p className="mt-1.5 text-xs text-faint">
                Changing the email on an account is not supported yet.
              </p>
            </div>

            <div>
              <label htmlFor="company" className="label">
                Company
              </label>
              <input
                id="company"
                type="text"
                value={settings.company}
                onChange={(event) => patch("company", event.target.value)}
                className="field"
                placeholder="Acme Inc."
              />
            </div>
          </div>
        </section>

        <section id="preferences" className="card p-5">
          <h2 className="text-[15px] font-semibold">Screening defaults</h2>

          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="defaultPositionTitle" className="label">
                Default position title
              </label>
              <input
                id="defaultPositionTitle"
                type="text"
                value={settings.defaultPositionTitle}
                onChange={(event) =>
                  patch("defaultPositionTitle", event.target.value)
                }
                className="field"
                placeholder="e.g. Senior ML Engineer"
              />
              <p className="mt-1.5 text-xs text-faint">
                Prefilled when you open the screening panel. You can always
                change it per batch.
              </p>
            </div>

            <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line p-3.5">
              <input
                type="checkbox"
                checked={settings.emailOnCompletion}
                onChange={(event) =>
                  patch("emailOnCompletion", event.target.checked)
                }
                className="mt-0.5 size-4 accent-[var(--brand)]"
              />
              <span>
                <span className="block text-[13px] font-medium">
                  Email me when a batch finishes
                </span>
                <span className="mt-0.5 block text-xs text-faint">
                  Saved as a preference. Delivery is not implemented yet — the
                  backend has no mail transport.
                </span>
              </span>
            </label>
          </div>
        </section>

        <section className="card p-5">
          <h2 className="text-[15px] font-semibold">Appearance</h2>

          <div
            role="radiogroup"
            aria-label="Theme"
            className="mt-4 inline-flex rounded-lg border border-line bg-bg-accent p-0.5"
          >
            {THEMES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={settings.theme === value}
                onClick={() => patch("theme", value)}
                className={`btn btn-sm ${
                  settings.theme === value
                    ? "bg-panel text-text shadow-sm"
                    : "text-muted hover:text-text"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="mt-2.5 text-xs text-faint">
            Applied when you save. &ldquo;System&rdquo; follows your operating
            system setting.
          </p>
        </section>

        <div className="flex items-center justify-end gap-3">
          {status === "saved" ? (
            <span className="flex items-center gap-1.5 text-[13px] text-positive">
              <CheckIcon size={15} />
              Saved
            </span>
          ) : null}

          <button
            type="submit"
            disabled={!dirty || status === "saving"}
            className="btn btn-md btn-primary"
          >
            {status === "saving" ? <SpinnerIcon size={16} /> : null}
            {status === "saving" ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
