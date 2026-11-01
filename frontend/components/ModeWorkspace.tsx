"use client";

import { useAuth } from "@/components/Auth";
import { Workspace } from "@/components/Workspace";

/** Each mode is a separate workspace: nothing private stays on screen after switching to public. */
export function ModeWorkspace() {
  const { mode } = useAuth();
  return <Workspace key={mode} />;
}
