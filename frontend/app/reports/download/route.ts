import { NextRequest, NextResponse } from "next/server";

import { API_URL } from "@/lib/api";

// A plain proxy: forwards the query string to GET /reports/{type} on the
// backend and streams its bytes/headers straight back. No logic lives
// here -- this exists only so the browser downloads the file via a
// same-origin navigation instead of the frontend needing to expose
// API_URL (or CORS) to the client.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const type = params.get("type");
  if (!type) {
    return NextResponse.json(
      { error: { code: "bad_request", message: "type is required", detail: null } },
      { status: 400 }
    );
  }

  const upstreamUrl = new URL(`/reports/${type}`, API_URL);
  for (const [key, value] of params.entries()) {
    if (key === "type" || value === "") continue;
    upstreamUrl.searchParams.set(key, value);
  }

  const appSharedSecret = process.env.APP_SHARED_SECRET;
  const upstream = await fetch(upstreamUrl, {
    cache: "no-store",
    headers: appSharedSecret ? { "x-app-secret": appSharedSecret } : {},
  });
  const body = await upstream.arrayBuffer();

  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition": upstream.headers.get("Content-Disposition") ?? "attachment",
    },
  });
}
