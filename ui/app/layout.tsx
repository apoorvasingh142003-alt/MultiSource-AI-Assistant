import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/Providers";
import AuthGate from "@/components/AuthGate";

export const metadata: Metadata = {
  title: "AI Business Assistant",
  description:
    "Multi-source retrieval & orchestration — upload PDFs and SQLite databases, ask questions, and inspect grounded, cited answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AuthGate>{children}</AuthGate>
        </Providers>
      </body>
    </html>
  );
}
