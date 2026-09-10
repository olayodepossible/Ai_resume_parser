import Link from "next/link";

import { LogoMark } from "@/components/icons";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col px-6 py-8 sm:px-10">
        <Link href="/" className="flex items-center gap-2.5 self-start">
          <LogoMark size={26} className="text-brand" />
          <span className="text-[15px] font-semibold tracking-tight">
            Shortlist
          </span>
        </Link>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">{children}</div>
        </div>
      </div>

      {/* Decorative panel; hidden on narrow screens where it would only push
          the form below the fold. */}
      <aside className="hidden border-l border-line bg-bg-accent lg:flex lg:flex-col lg:justify-center lg:px-14">
        <blockquote className="max-w-md">
          <p className="text-2xl leading-snug font-medium tracking-tight text-balance">
            &ldquo;Two hundred applications, one afternoon, and a shortlist I
            could actually explain to the hiring manager.&rdquo;
          </p>
          <footer className="mt-6 text-[13px] text-muted">
            Let AI get the job done...
          </footer>
        </blockquote>

        <dl className="mt-14 grid grid-cols-2 gap-6 border-t border-line pt-10">
          <div>
            <dt className="text-[13px] text-muted">Resumes per batch</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">25</dd>
          </div>
          <div>
            <dt className="text-[13px] text-muted">Screened in parallel</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">4</dd>
          </div>
        </dl>
      </aside>
    </div>
  );
}
