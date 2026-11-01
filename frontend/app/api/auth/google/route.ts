import { randomBytes } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";
import { authSettings, OAUTH_COOKIE, safeNext } from "@/lib/authToken";

/** Step 1 of the Google sign-in. It asks only for the account's ID and name, not the email address. */
export async function GET(request: NextRequest) {
  const settings = authSettings();
  if (!settings) return new Response(null, { status: 404 });
  const { origin } = request.nextUrl;
  const state = randomBytes(24).toString("base64url");
  const next = safeNext(request.nextUrl.searchParams.get("next"), origin);
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", settings.clientId);
  url.searchParams.set("redirect_uri", `${origin}/api/auth/google/callback`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid profile");
  url.searchParams.set("state", state);
  url.searchParams.set("prompt", "select_account");
  const response = NextResponse.redirect(url);
  response.cookies.set(OAUTH_COOKIE, JSON.stringify({ state, next }), {
    httpOnly: true,
    secure: origin.startsWith("https:"),
    sameSite: "lax",
    path: "/api/auth",
    maxAge: 600,
  });
  return response;
}
