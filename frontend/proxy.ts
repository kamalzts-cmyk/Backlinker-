// Next.js 16 renamed middleware.ts to proxy.ts (same mechanism, new
// name/export) -- see node_modules/next/dist/docs/.../proxy.md.
//
// Gates every page behind the shared password when APP_SHARED_SECRET is
// set (public deployments); a no-op in local dev, where it's unset --
// matching the backend's SharedSecretMiddleware (backend/app/api/auth_gate.py).

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_COOKIE, expectedSessionToken } from "@/lib/auth";

export default function proxy(request: NextRequest) {
  const secret = process.env.APP_SHARED_SECRET;
  if (!secret) return NextResponse.next();

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token === expectedSessionToken(secret)) return NextResponse.next();

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
