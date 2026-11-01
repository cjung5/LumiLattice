// TEMPORARY: what Meta tells a server on Vercel's network. Remove after the test.
export const dynamic = "force-dynamic";

const BASE = "https://api.meta.ai/v1";

export async function GET() {
  const key = process.env.MODEL_API_KEY;
  if (!key) return Response.json({ detail: "MODEL_API_KEY is not set." }, { status: 503 });
  const headers = { Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
  const listed = await fetch(`${BASE}/models`, { headers, signal: AbortSignal.timeout(20000) });
  const models = listed.ok ? ((await listed.json()).data ?? []).map((m: { id: string }) => m.id) : [];
  const location = await (await fetch("https://ipinfo.io/json", { signal: AbortSignal.timeout(8000) })).json();
  const call = await fetch(`${BASE}/responses`, {
    method: "POST",
    headers,
    body: JSON.stringify({ model: "muse-spark-1.3", input: "Reply OK", max_output_tokens: 16 }),
    signal: AbortSignal.timeout(30000),
  });
  return Response.json({
    models_status: listed.status,
    models,
    server_country: location.country,
    server_org: location.org,
    vercel_region: process.env.VERCEL_REGION ?? null,
    muse_spark_1_3_status: call.status,
  });
}
