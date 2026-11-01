import { NextResponse, type NextRequest } from "next/server";
import { accountTag, authSettings, OAUTH_COOKIE, safeNext, SESSION_COOKIE, SESSION_SECONDS, signToken } from "@/lib/authToken";

const DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration";

/** Step 2: Google returns here. Only the account's ID and a short tag are kept, in a signed cookie. */
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
    const signal = AbortSignal.timeout(10_000);
    const discovery = await fetch(DISCOVERY, { signal });
    const { token_endpoint: tokenUrl, userinfo_endpoint: userUrl } = (await discovery.json()) as {
      token_endpoint: string;
      userinfo_endpoint: string;
    };
    const tokenResponse = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: settings.clientId,
        client_secret: settings.clientSecret,
        code,
        grant_type: "authorization_code",
        redirect_uri: `${origin}/api/auth/google/callback`,
      }),
      signal,
    });
    const { access_token: accessToken } = (await tokenResponse.json()) as { access_token?: string };
    if (!accessToken) return failed();
    const userResponse = await fetch(userUrl, { headers: { Authorization: `Bearer ${accessToken}` }, signal });
    if (!userResponse.ok) return failed();
    const user = (await userResponse.json()) as { sub?: string; name?: string; given_name?: string; family_name?: string };
    if (!user.sub) return failed();
    // sub is the account's permanent ID. The Google access token is not stored: the app needs
    // nothing else from Google.
    const session = signToken(
      {
        sub: `google:${user.sub}`,
        name: accountTag(user),
        aud: "session",
        exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
      },
      settings.secret,
    );
    return finish(new URL(next, origin), session);
  } catch {
    return failed();
  }
}
