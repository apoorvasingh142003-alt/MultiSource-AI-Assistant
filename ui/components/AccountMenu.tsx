"use client";
import React from "react";
import { signOut, useSession } from "next-auth/react";
import { Icons, cn } from "@/components/ui";
import SheetsConnect from "@/components/SheetsConnect";
import DriveConnect from "@/components/DriveConnect";
import HubSpotConnect from "@/components/HubSpotConnect";
import TelegramConnect from "@/components/TelegramConnect";
import WhatsAppConnect from "@/components/WhatsAppConnect";

const AUTH_ON = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

// The signed-in identity + connected-apps launcher, styled like the account/apps menu in
// Gmail: a circular avatar in the top bar that opens a card with the user's identity, a grid
// of connectable apps (official brand icons + live status), and sign-out.
export default function AccountMenu() {
  if (!AUTH_ON) return null;
  return <Menu />;
}

function Avatar({ name, email, image, size = 32 }: { name?: string | null; email?: string | null; image?: string | null; size?: number }) {
  const initial = (name || email || "?").slice(0, 1).toUpperCase();
  if (image) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={image} alt="" className="rounded-full object-cover" style={{ height: size, width: size }} referrerPolicy="no-referrer" />;
  }
  return (
    <span className="grid place-items-center rounded-full bg-brand-gradient font-semibold text-white"
      style={{ height: size, width: size, fontSize: size * 0.42 }}>
      {initial}
    </span>
  );
}

function Menu() {
  const { data: session, status } = useSession();
  const [open, setOpen] = React.useState(false);
  const [openApp, setOpenApp] = React.useState<string | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onEsc);
    return () => { window.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onEsc); };
  }, [open]);

  if (status !== "authenticated" || !session?.user) return null;
  const user = session.user;
  const toggleApp = (id: string) => setOpenApp((cur) => (cur === id ? null : id));

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title={user.email || "Account"}
        aria-label="Account menu"
        className={cn(
          "grid place-items-center rounded-full ring-2 ring-offset-2 ring-offset-app transition hover:opacity-90",
          open ? "ring-accent/60" : "ring-line")}
      >
        <Avatar name={user.name} email={user.email} image={user.image} size={30} />
      </button>

      {open && (
        <div className="animate-scale-in absolute right-0 z-50 mt-2 w-80 origin-top-right overflow-hidden rounded-2xl border border-line bg-overlay shadow-pop">
          {/* identity */}
          <div className="flex items-center gap-3 border-b border-line px-4 py-4">
            <Avatar name={user.name} email={user.email} image={user.image} size={44} />
            <div className="min-w-0">
              {user.name && <div className="truncate text-sm font-semibold text-fg">{user.name}</div>}
              <div className="truncate text-xs text-muted">{user.email}</div>
            </div>
          </div>

          {/* connected apps */}
          <div className="px-4 py-3.5">
            <div className="mb-2.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">
              <Icons.link className="h-3.5 w-3.5" /> Connected apps &amp; data
            </div>
            <div className="space-y-2">
              <SheetsConnect open={openApp === "sheets"} onToggle={() => toggleApp("sheets")} />
              <DriveConnect open={openApp === "drive"} onToggle={() => toggleApp("drive")} />
              <HubSpotConnect open={openApp === "hubspot"} onToggle={() => toggleApp("hubspot")} />
              <TelegramConnect open={openApp === "telegram"} onToggle={() => toggleApp("telegram")} />
              <WhatsAppConnect open={openApp === "whatsapp"} onToggle={() => toggleApp("whatsapp")} />
            </div>
          </div>

          {/* sign out */}
          <div className="border-t border-line p-2">
            <button
              onClick={() => signOut()}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/10 dark:hover:text-rose-400"
            >
              <Icons.logout className="h-4 w-4" /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
