import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth";

// NextAuth's own endpoints (/api/auth/*). These are filesystem routes, so they take
// precedence over the /api/* proxy rewrite in next.config.js and are handled locally.
const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
