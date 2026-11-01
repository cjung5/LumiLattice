import { NextResponse, type NextRequest } from "next/server";
import { API_TOKEN_SECONDS, authSettings, readToken, SESSION_COOKIE, signToken } from "@/lib/authToken";

/** Who is signed in, with a short-lived token for the backend. The session cookie stays HTTP-only. */
export async function GET(request: NextRequest) {
  const settings = authSettings();
  const headers = { "Cache-Control": "no-store" };
  if (!settings) return NextResponse.json({ enabled: false, name: null, token: null, expires_at: 0 }, { headers });
  const session = readToken(request.cookies.get(SESSION_COOKIE)?.value, settings.secret, "session");
  if (!session) return NextResponse.json({ enabled: true, name: null, token: null, expires_at: 0 }, { headers });
  const exp = Math.floor(Date.now() / 1000) + API_TOKEN_SECONDS;
  const token = signToken({ sub: session.sub, name: session.name, aud: "api", exp }, settings.secret);
  return NextResponse.json({ enabled: true, name: session.name, token, expires_at: exp }, { headers });
}
