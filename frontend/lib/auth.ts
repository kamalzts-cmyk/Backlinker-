// Shared-password gate for public deployments -- see docs/DEPLOYMENT.md.
// This project has no real multi-user auth (see ../docs/ARCHITECTURE.md
// §9): this is a deliberately minimal single-password bolt-on, not a
// session/identity system. The cookie holds a deterministic hash of the
// shared secret, never the raw password, but it's still exactly as
// strong as the one shared password -- don't reuse a sensitive password
// here.

import { createHash } from "node:crypto";

export const SESSION_COOKIE = "li_session";

export function expectedSessionToken(secret: string): string {
  return createHash("sha256").update(`linkintel-session:${secret}`).digest("hex");
}
