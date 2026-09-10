"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth-context";

import { Avatar } from "./avatar";
import { ChevronDownIcon, LogOutIcon, SettingsIcon, UserIcon } from "./icons";

export function ProfileMenu() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape — the two ways a user expects to
  // dismiss a menu they opened by accident.
  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) return null;

  function handleSignOut() {
    setOpen(false);
    logout();
    router.replace("/");
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="btn btn-sm btn-ghost gap-1.5 pr-2 pl-1.5"
      >
        <Avatar name={user.fullName || user.email} size={26} />
        <span className="hidden max-w-32 truncate sm:inline">
          {user.fullName || user.email}
        </span>
        <ChevronDownIcon size={14} />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-64 overflow-hidden rounded-xl border border-line bg-panel-raised shadow-panel"
        >
          <div className="flex items-center gap-3 border-b border-line px-3.5 py-3">
            <Avatar name={user.fullName || user.email} size={36} />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold">
                {user.fullName || "Unnamed"}
              </p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
          </div>

          {user.settings.company ? (
            <p className="border-b border-line px-3.5 py-2 text-xs text-faint">
              {user.settings.company}
            </p>
          ) : null}

          <div className="p-1.5">
            <Link
              href="/dashboard/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-text hover:bg-bg-accent"
            >
              <UserIcon size={16} className="text-faint" />
              Profile
            </Link>

            <Link
              href="/dashboard/settings#preferences"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-text hover:bg-bg-accent"
            >
              <SettingsIcon size={16} className="text-faint" />
              Settings
            </Link>

            <button
              type="button"
              role="menuitem"
              onClick={handleSignOut}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-negative hover:bg-negative/8"
            >
              <LogOutIcon size={16} />
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
