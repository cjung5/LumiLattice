import type { NextRequest } from "next/server";
import { API_BASE_URL } from "@/lib/api";

// The hosting service looks up the country and sets one of these headers. The IP address stays
// there: only the two-letter code goes on to the backend. Vercel overwrites its header, so a
// browser cannot choose its own country on the deployed site.
const COUNTRY_HEADERS = ["x-vercel-ip-country", "cf-ipcountry"];
const NOT_A_COUNTRY = new Set(["XX", "T1", "ZZ"]);

export async function POST(request: NextRequest) {
  const raw = COUNTRY_HEADERS.map((name) => request.headers.get(name)).find(Boolean) ?? "";
  const country = /^[A-Z]{2}$/.test(raw) && !NOT_A_COUNTRY.has(raw) ? raw : null;
  const secret = process.env.VISIT_SECRET;
  try {
    await fetch(`${API_BASE_URL}/api/visits`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(secret ? { "X-Visit-Secret": secret } : {}) },
      body: JSON.stringify({ country }),
    });
  } catch {
    // A missed count must not disturb the page.
  }
  return new Response(null, { status: 204 });
}
