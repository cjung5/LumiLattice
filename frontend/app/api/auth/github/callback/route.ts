import { NextResponse, type NextRequest } from "next/server";
import { authSettings, OAUTH_COOKIE, safeNext, SESSION_COOKIE, SESSION_SECONDS, signToken } from "@/lib/authToken";

/** Step 2: GitHub returns here. Only the account's ID and user name are kept, in a signed cookie. */
export async function GET(request: NextRequest) {
  const settings = authSettings();
  if (!settings) return new Response(null, { status: 404 });
  const { origin, searchParams } = request.nextUrl;

  let saved: { state?: string; next?: string } = {};
  try {
    saved = JSON.parse(request.cookies.get(OAUTH_COOKIE)?.value ?? "{}");
  } catch {
    // A bad cookie fails the state check below.
  }
  const next = safeNext(saved.next ?? "/", origin);
  const finish = (url: URL, session?: string) => {
    const response = NextResponse.redirect(url);
    response.cookies.delete({ name: OAUTH_COOKIE, path: "/api/auth" });
    if (session) {
      response.cookies.set(SESSION_COOKIE, session, {
        httpOnly: true,
        secure: origin.startsWith("https:"),
        sameSite: "lax",
        path: "/",
        maxAge: SESSION_SECONDS,
      });
    }
    return response;
  };
  const failed = () => {
    const url = new URL(next, origin);
    url.searchParams.set("signin", "failed");
    return finish(url);
  };

  const code = searchParams.get("code");
  const state = searchParams.get("state");
  if (!code || !state || state !== saved.state) return failed();

  try {
    const tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: settings.clientId,
        client_secret: settings.clientSecret,
        code,
        redirect_uri: `${origin}/api/auth/github/callback`,
      }),
      signal: AbortSignal.timeout(10_000),
    });
    const { access_token: accessToken } = (await tokenResponse.json()) as { access_token?: string };
    if (!accessToken) return failed();
    const userResponse = await fetch("https://api.github.com/user", {
      headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${accessToken}`, "User-Agent": "LumiLattice" },
      signal: AbortSignal.timeout(10_000),
    });
    if (!userResponse.ok) return failed();
    const user = (await userResponse.json()) as { id?: number; login?: string };
    if (!user.id || !user.login) return failed();
    // The GitHub access token is not stored: the app needs nothing else from GitHub.
    const session = signToken(
      { sub: `github:${user.id}`, login: user.login, aud: "session", exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS },
      settings.secret,
    );
    return finish(new URL(next, origin), session);
  } catch {
    return failed();
  }
}
