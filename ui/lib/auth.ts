import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

// Google sign-in (open signup). We request the Sheets read-only scope up-front so the
// same consent lets the assistant read a user's sheets later (Increment 4), and keep the
// Google access/refresh tokens in the NextAuth JWT for that use.
export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
      authorization: {
        params: {
          scope:
            "openid email profile https://www.googleapis.com/auth/spreadsheets.readonly",
          access_type: "offline",
          prompt: "consent",
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
      return token;
    },
    async session({ session, token }) {
      if (session.user) (session.user as { id?: string }).id = token.sub as string;
      return session;
    },
  },
};
