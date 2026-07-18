import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
import { SignJWT } from "jose";

// Bridge the Google session to the backend: for every /api/* call the browser makes
// (proxied to FastAPI), read the NextAuth session and attach a short-lived HS256
// identity JWT the backend verifies with the shared ABA_AUTH_SECRET. NextAuth's own
// /api/auth/* routes are left untouched. If there is no session, no header is added
// and the backend (when ABA_AUTH_ENABLED) replies 401 → the UI shows the sign-in gate.
export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/api/auth")) return NextResponse.next();

  const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
  const headers = new Headers(req.headers);

  if (token?.sub && process.env.ABA_AUTH_SECRET) {
    const secret = new TextEncoder().encode(process.env.ABA_AUTH_SECRET);
    const jwt = await new SignJWT({
      email: (token.email as string) ?? "",
      name: (token.name as string) ?? "",
      picture: (token.picture as string) ?? "",
    })
      .setProtectedHeader({ alg: "HS256", typ: "JWT" })
      .setSubject(token.sub as string)
      .setIssuedAt()
      .setExpirationTime("10m")
      .sign(secret);
    headers.set("authorization", `Bearer ${jwt}`);
    // Forward the user's Google access token (server-side only) so the backend can call
    // Google APIs (Sheets) on their behalf. Set from the session, never from the client.
    if (token.googleAccessToken) {
      headers.set("x-google-access-token", token.googleAccessToken as string);
    } else {
      headers.delete("x-google-access-token");
    }
  } else {
    // No browser session: let a client-supplied Authorization header PASS THROUGH to the
    // backend, which verifies the HS256 signature against ABA_AUTH_SECRET itself (a forged
    // token fails there). This is what lets programmatic clients — above all external MCP
    // clients hitting /api/mcp (Phase 6) — authenticate with a backend-issued bearer token
    // when there is no Google session. The Google access token is still never trusted from
    // the client: it is only ever set server-side from the session above.
    headers.delete("x-google-access-token");
  }

  return NextResponse.next({ request: { headers } });
}

// Only run on backend API calls (keeps auth pages/assets fast).
export const config = { matcher: ["/api/:path*"] };
