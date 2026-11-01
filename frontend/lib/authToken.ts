import { createHmac, timingSafeEqual } from "node:crypto";

// Server only. The same token format as backend/app/auth.py: base64url(JSON) + "." + base64url(HMAC).
// The session cookie and the API token have different audiences, so one cannot act as the other.
export type TokenPayload = { sub: string; name: string; aud: "session" | "api"; exp: number };

export const SESSION_COOKIE = "ll_session";
export const OAUTH_COOKIE = "ll_oauth";
export const SESSION_SECONDS = 7 * 24 * 3600;
export const API_TOKEN_SECONDS = 15 * 60;

function signature(body: string, secret: string) {
  return createHmac("sha256", secret).update(body).digest("base64url");
}

export function signToken(payload: TokenPayload, secret: string) {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${body}.${signature(body, secret)}`;
}

export function readToken(token: string | undefined, secret: string, aud: TokenPayload["aud"]) {
  const [body, given] = (token ?? "").split(".");
  if (!body || !given) return null;
  const expected = Buffer.from(signature(body, secret));
  const actual = Buffer.from(given);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, "base64url").toString()) as TokenPayload;
    return payload.aud === aud && payload.exp > Date.now() / 1000 ? payload : null;
  } catch {
    return null;
  }
}

/** A short tag such as "C. Jung". The full name is not kept. Google does not promise any name. */
export function accountTag(user: { name?: string; given_name?: string; family_name?: string }) {
  const parts = (user.name ?? "").trim().split(/\s+/).filter(Boolean);
  const given = user.given_name?.trim() || parts[0];
  const family = user.family_name?.trim() || (parts.length > 1 ? parts[parts.length - 1] : "");
  if (!given) return family || "Researcher";
  const initial = `${[...given][0].toUpperCase()}.`;
  return (family ? `${initial} ${family}` : initial).slice(0, 60);
}

/** All three are needed. Without them, the site offers only public mode. */
export function authSettings() {
  const secret = process.env.AUTH_SECRET;
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  return secret && secret.length >= 32 && clientId && clientSecret ? { secret, clientId, clientSecret } : null;
}

/** Only a path on this site, so a crafted sign-in link cannot send someone to another site. */
export function safeNext(next: string | null, origin: string) {
  try {
    const url = new URL(next ?? "/", origin);
    return url.origin === origin && !(next ?? "").includes("\\") ? `${url.pathname}${url.search}` : "/";
  } catch {
    return "/";
  }
}
