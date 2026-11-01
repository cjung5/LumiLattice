import { timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

// The Meta Model API lists no models for requests from Railway's network (checked 2026-11-01),
// so the backend sends its Muse Spark calls through this route. Only the backend can use it:
// it sends VISIT_SECRET, which both servers already share.
export const maxDuration = 120;

const META_API_URL = "https://api.meta.ai/v1";
const ALLOWED_PATHS = new Set(["responses", "chat/completions"]);

function isBackend(given: string | null): boolean {
  const expected = process.env.VISIT_SECRET;
  if (!expected || !given) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if (!isBackend(request.headers.get("x-proxy-secret"))) return new Response(null, { status: 403 });
  const path = (await params).path.join("/");
  if (!ALLOWED_PATHS.has(path)) return new Response(null, { status: 404 });
  const key = process.env.MODEL_API_KEY;
  if (!key) return Response.json({ error: { message: "MODEL_API_KEY is not set on the frontend server." } }, { status: 503 });
  const upstream = await fetch(`${META_API_URL}/${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: await request.text(),
    signal: AbortSignal.timeout(115_000),
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
