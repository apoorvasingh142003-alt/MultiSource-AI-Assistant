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
      const t = token as Record<string, unknown>;
      // On (initial or incremental) sign-in, capture the tokens + expiry.
      if (account) {
        if (profile && (profile as { sub?: string }).sub) token.sub = (profile as { sub: string }).sub;
        if (account.access_token) t.googleAccessToken = account.access_token;
        if (account.refresh_token) t.googleRefreshToken = account.refresh_token;
        if (account.scope) t.scope = account.scope;
        t.accessTokenExpires = account.expires_at
          ? account.expires_at * 1000
          : Date.now() + 3600 * 1000;
        return token;
      }
      // Still valid? keep it.
      const exp = t.accessTokenExpires as number | undefined;
      if (exp && Date.now() < exp - 60_000) return token;
      // Expired → refresh with the stored refresh token (from the Sheets offline consent).
      const refresh = t.googleRefreshToken as string | undefined;
      if (!refresh) return token;
      try {
        const res = await fetch("https://oauth2.googleapis.com/token", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            client_id: process.env.GOOGLE_CLIENT_ID || "",
            client_secret: process.env.GOOGLE_CLIENT_SECRET || "",
            grant_type: "refresh_token",
            refresh_token: refresh,
          }),
        });
        const data = await res.json();
        if (res.ok && data.access_token) {
          t.googleAccessToken = data.access_token;
          t.accessTokenExpires = Date.now() + (data.expires_in ?? 3600) * 1000;
          if (data.refresh_token) t.googleRefreshToken = data.refresh_token;
          if (data.scope) t.scope = data.scope;
        }
      } catch {
        /* keep the old token; user can reconnect */
      }
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
