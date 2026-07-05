"use client";
import { signIn, signOut, useSession } from "next-auth/react";
import TelegramConnect from "@/components/TelegramConnect";
import SheetsConnect from "@/components/SheetsConnect";
import HubSpotConnect from "@/components/HubSpotConnect";

// When auth is disabled (dev/single-tenant) this is a passthrough. When enabled, it gates
// the whole app behind Google sign-in and shows a compact signed-in chip with sign-out.
const AUTH_ON = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  if (!AUTH_ON) return <>{children}</>;
  return <Gate>{children}</Gate>;
}

function Gate({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-slate-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (status === "unauthenticated" || !session) {
    return (
      <div className="min-h-screen grid place-items-center bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 px-4">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl p-8 text-center">
          <div className="mx-auto mb-5 h-12 w-12 rounded-xl bg-indigo-600 grid place-items-center text-white text-xl font-bold">A</div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Multi-Source Knowledge Assistant
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            Sign in to access your private workspace — your documents, chats and connections
            stay isolated to your account.
          </p>
          <button
            onClick={() => signIn("google")}
            className="mt-6 w-full inline-flex items-center justify-center gap-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
          >
            <GoogleIcon />
            Continue with Google
          </button>
        </div>
      </div>
    );
  }

  const user = session.user;
  return (
    <>
      <div className="fixed top-3 right-3 z-50 flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur px-2 py-1 shadow-sm">
        {user?.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.image} alt="" className="h-6 w-6 rounded-full" />
        ) : (
          <div className="h-6 w-6 rounded-full bg-indigo-500 text-white grid place-items-center text-xs">
            {(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}
          </div>
        )}
        <span className="text-xs text-slate-600 dark:text-slate-300 max-w-[9rem] truncate">
          {user?.email}
        </span>
        <SheetsConnect />
        <HubSpotConnect />
        <TelegramConnect />
        <button
          onClick={() => signOut()}
          className="text-xs font-medium text-slate-500 hover:text-rose-600 px-1"
          title="Sign out"
        >
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}

function GoogleIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  );
}
