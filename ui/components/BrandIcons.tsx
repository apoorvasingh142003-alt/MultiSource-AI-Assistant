"use client";
import React from "react";

/* Official-style brand marks, drawn as self-contained SVGs (no external assets, no network).
   Each keeps the brand's real colors so they read instantly next to the product's own icon set. */

type P = { className?: string };
const box = (className?: string) => `h-5 w-5 ${className ?? ""}`.trim();

export function GoogleMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
    </svg>
  );
}

export function SheetsMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <path fill="#188038" d="M6 2h8l6 6v12.5A1.5 1.5 0 0 1 18.5 22h-13A1.5 1.5 0 0 1 4 20.5v-17A1.5 1.5 0 0 1 5.5 2z" />
      <path fill="#34A853" d="M14 2l6 6h-6z" opacity=".9" />
      <path fill="#fff" d="M8 11.5h8v6.2H8zM9.4 12.9v1.1h2.1v-1.1zm3.5 0v1.1H15v-1.1zM9.4 15.1v1.2h2.1v-1.2zm3.5 0v1.2H15v-1.2z" />
    </svg>
  );
}

export function TelegramMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <defs>
        <linearGradient id="tg-g" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#37AEE2" />
          <stop offset="1" stopColor="#1E96C8" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="10" fill="url(#tg-g)" />
      <path fill="#fff" d="M17.6 7.4l-2.03 9.58c-.15.68-.55.85-1.12.53l-3.1-2.28-1.5 1.44c-.16.17-.3.3-.62.3l.22-3.16 5.75-5.2c.25-.22-.05-.34-.39-.12l-7.1 4.47-3.06-.96c-.66-.2-.68-.66.14-.98l11.97-4.62c.55-.2 1.03.13.85.98z" />
    </svg>
  );
}

export function WhatsAppMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <path fill="#25D366" d="M12 2a9.9 9.9 0 0 0-8.5 15l-1.3 4.8 4.9-1.3A9.9 9.9 0 1 0 12 2z" />
      <path fill="#fff" d="M9.1 7.1c-.2-.45-.4-.46-.58-.47l-.5-.01a.96.96 0 0 0-.69.32c-.24.26-.9.88-.9 2.14s.92 2.48 1.05 2.66c.13.17 1.8 2.88 4.46 3.92 2.2.87 2.65.7 3.13.65.48-.04 1.54-.63 1.76-1.24.22-.6.22-1.13.15-1.24-.06-.1-.24-.17-.5-.3-.27-.13-1.55-.77-1.79-.85-.24-.09-.41-.13-.59.13-.17.26-.67.85-.82 1.02-.15.18-.3.2-.56.07-.27-.13-1.11-.41-2.12-1.31-.78-.7-1.31-1.56-1.46-1.82-.15-.26-.02-.4.11-.53.12-.12.27-.31.4-.46.14-.16.18-.27.27-.44.09-.18.05-.33-.02-.46-.07-.13-.58-1.44-.8-1.96z" />
    </svg>
  );
}

export function DriveMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <path fill="#FFBA00" d="M8.65 3h6.7L9.1 14.4 5.75 20 2.4 14.4z" />
      <path fill="#4285F4" d="M15.35 3l6.25 11.4h-6.7L8.65 3z" />
      <path fill="#1EA362" d="M9.1 14.4h12.5L18.25 20H5.75z" />
    </svg>
  );
}

export function HubSpotMark({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={box(className)} aria-hidden="true">
      <g fill="#FF7A59">
        <path d="M16.6 8.6V6.2a1.85 1.85 0 0 0 1.07-1.67v-.06A1.85 1.85 0 0 0 15.82 2.6h-.06a1.85 1.85 0 0 0-1.85 1.85v.06A1.85 1.85 0 0 0 15 6.2v2.4a5.24 5.24 0 0 0-2.5 1.1L6.2 4.66a2.09 2.09 0 1 0-.98 1.28l6.2 4.83a5.28 5.28 0 0 0 .08 5.97l-1.89 1.89a1.7 1.7 0 1 0 1.12 1.16l1.87-1.87a5.29 5.29 0 1 0 4-8.32zm-.79 7.94a2.71 2.71 0 1 1 0-5.42 2.71 2.71 0 0 1 0 5.42z" />
      </g>
    </svg>
  );
}

/* Map an integration key → mark + accent, so the account menu can render them uniformly. */
export const BRAND: Record<
  string,
  { label: string; Mark: (p: P) => JSX.Element; ring: string; glow: string }
> = {
  sheets: { label: "Google Sheets", Mark: SheetsMark, ring: "ring-emerald-200 dark:ring-emerald-500/30", glow: "bg-emerald-50 dark:bg-emerald-500/10" },
  drive: { label: "Google Drive", Mark: DriveMark, ring: "ring-blue-200 dark:ring-blue-500/30", glow: "bg-blue-50 dark:bg-blue-500/10" },
  hubspot: { label: "HubSpot", Mark: HubSpotMark, ring: "ring-orange-200 dark:ring-orange-500/30", glow: "bg-orange-50 dark:bg-orange-500/10" },
  telegram: { label: "Telegram", Mark: TelegramMark, ring: "ring-sky-200 dark:ring-sky-500/30", glow: "bg-sky-50 dark:bg-sky-500/10" },
  whatsapp: { label: "WhatsApp", Mark: WhatsAppMark, ring: "ring-green-200 dark:ring-green-500/30", glow: "bg-green-50 dark:bg-green-500/10" },
};
