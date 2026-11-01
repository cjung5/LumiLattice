import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/authToken";

export async function POST() {
  const response = new NextResponse(null, { status: 204 });
  response.cookies.delete({ name: SESSION_COOKIE, path: "/" });
  return response;
}
