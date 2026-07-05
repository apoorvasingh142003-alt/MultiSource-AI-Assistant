import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

// Google sign-in (open signup). Only basic, NON-sensitive scopes at login (openid/email/
// profile) so the app needs no Google sensitive-scope verification to publish. The Sheets
// read-only scope is requested later via INCREMENTAL authorization, only when a user
// connects a sheet (Increment 4) — keeping sign-in frictionless and easy to verify.
export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
      authorization: {
        params: {
          scope: "openid email profile",
        },
      },
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account, profile }) {
      if (profile && (profile as { sub?: string }).sub) {
        token.sub = (profile as { sub: string }).sub;
      }
      if (account?.access_token) (token as Record<string, unknown>).googleAccessToken = account.access_token;
      if (account?.refresh_token) (token as Record<string, unknown>).googleRefreshToken = account.refresh_token;
      if (account?.scope) (token as Record<string, unknown>).scope = account.scope;
      return token;
    },
    async session({ session, token }) {
      if (session.user) (session.user as { id?: string }).id = token.sub as string;
      // Surface whether the Sheets scope has been granted (never expose the token itself).
      const scope = (token as Record<string, unknown>).scope;
      (session as unknown as Record<string, unknown>).sheetsConnected =
        typeof scope === "string" && scope.includes("spreadsheets");
      return session;
    },
  },
};
