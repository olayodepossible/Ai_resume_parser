"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LogoMark, SettingsIcon, SpinnerIcon } from "@/components/icons";
import { ProfileMenu } from "@/components/profile-menu";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading } = useAuth();

  // Client-side only: the token lives in localStorage, which middleware
  // cannot see. Swap this for a cookie session when auth becomes real.
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <SpinnerIcon size={22} className="text-faint" />
        <span className="sr-only">Loading your account</span>
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <LogoMark size={26} className="text-brand" />
            <span className="text-[15px] font-semibold tracking-tight">
              Shortlist
            </span>
          </Link>

          <div className="flex items-center gap-1.5">
            <Link
              href="/dashboard/settings"
              aria-label="Settings"
              title="Settings"
              className="btn btn-ghost size-9 p-0"
            >
              <SettingsIcon size={18} />
            </Link>

            <ProfileMenu />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
