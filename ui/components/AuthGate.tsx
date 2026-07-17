"use client";
import { signIn, useSession } from "next-auth/react";
import { GoogleMark, SheetsMark, HubSpotMark, TelegramMark, WhatsAppMark } from "@/components/BrandIcons";

// When auth is disabled (dev/single-tenant) this is a passthrough. When enabled it gates the
// whole app behind Google sign-in. The signed-in account UI now lives in the header
// (AccountMenu) rather than a floating chip, so this only owns the loading + login screens.
const AUTH_ON = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  if (!AUTH_ON) return <>{children}</>;
  return <Gate>{children}</Gate>;
}

function Gate({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <div className="relative grid min-h-screen place-items-center overflow-hidden">
        <div className="aurora" />
        <div className="flex flex-col items-center gap-4">
          <BrandLogo />
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      </div>
    );
  }

  if (status === "unauthenticated" || !session) {
    return <LoginScreen />;
  }

  return <>{children}</>;
}

function BrandLogo({ size = 44 }: { size?: number }) {
  return (
    <div
      className="grid place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow"
      style={{ height: size, width: size }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
           strokeLinecap="round" strokeLinejoin="round" style={{ height: size * 0.5, width: size * 0.5 }}>
        <path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" />
      </svg>
    </div>
  );
}

function LoginScreen() {
  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden px-4 py-10">
      <div className="aurora" />

      <div className="relative grid w-full max-w-4xl gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:gap-10">
        {/* ---- left: brand + value props ---- */}
        <div className="hidden flex-col justify-center lg:flex">
          <div className="flex items-center gap-3">
            <BrandLogo />
            <div>
              <div className="text-lg font-bold text-fg">Nexus AI</div>
              <div className="text-xs text-muted">Adaptive Multi-Domain Intelligence</div>
            </div>
          </div>

          <h1 className="mt-8 text-[34px] font-extrabold leading-[1.1] tracking-tight text-fg">
            Answers you can <span className="text-gradient">actually trust</span>,
            grounded in your own data.
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-muted">
            Upload documents and databases, or connect Sheets and your CRM. Every reply streams
            with verifiable citations — never a confident guess.
          </p>

          <ul className="mt-7 space-y-3">
            {[
              { t: "Grounded & cited", d: "Hybrid retrieval with citation verification on every answer." },
              { t: "Your data, isolated", d: "A private workspace per account — nothing leaks across tenants." },
              { t: "Everywhere you work", d: "Chat on the web, Telegram and WhatsApp — same grounded engine." },
            ].map((f) => (
              <li key={f.t} className="flex items-start gap-3">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent-soft text-accent ring-1 ring-accent/20">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3"><path d="M20 6 9 17l-5-5" /></svg>
                </span>
                <span className="text-sm text-body">
                  <span className="font-semibold text-fg">{f.t}.</span> {f.d}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* ---- right: sign-in card ---- */}
        <div className="relative w-full self-center rounded-3xl border border-line bg-surface/80 p-8 shadow-pop backdrop-blur-xl">
          <div className="mb-6 flex flex-col items-center text-center lg:hidden">
            <BrandLogo />
            <h2 className="mt-3 text-lg font-bold text-fg">Nexus AI</h2>
          </div>

          <h2 className="text-center text-[22px] font-bold text-fg">Welcome</h2>
          <p className="mx-auto mt-1.5 max-w-xs text-center text-sm text-muted">
            Sign in to open your private workspace. New here? Your account is created automatically.
          </p>

          <button
            onClick={() => signIn("google")}
            className="group mt-7 flex w-full items-center justify-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-semibold text-fg shadow-sm transition hover:border-accent/40 hover:shadow-md active:scale-[0.99]"
          >
            <GoogleMark className="h-5 w-5" />
            Continue with Google
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 -translate-x-1 text-faint opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>

          <div className="mt-7">
            <div className="mb-3 flex items-center gap-3 text-[11px] font-medium uppercase tracking-widest text-faint">
              <span className="h-px flex-1 bg-line" /> Connects with <span className="h-px flex-1 bg-line" />
            </div>
            <div className="flex items-center justify-center gap-3">
              {[SheetsMark, HubSpotMark, TelegramMark, WhatsAppMark].map((Mark, i) => (
                <div key={i} className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-surface-2 transition hover:scale-105">
                  <Mark className="h-5 w-5" />
                </div>
              ))}
            </div>
          </div>

          <p className="mt-7 text-center text-[11px] leading-relaxed text-faint">
            By continuing you agree that your documents stay private to your account.
          </p>
        </div>
      </div>
    </div>
  );
}
