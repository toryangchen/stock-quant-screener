import type { ScreeningResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function fetchDates(): Promise<string[]> {
  const resp = await fetch(`${API_BASE}/api/screening/dates`);
  if (!resp.ok) {
    throw new Error(`fetch dates failed: ${resp.status}`);
  }
  const json = (await resp.json()) as { dates: string[] };
  return json.dates ?? [];
}

export async function fetchScreening(date: string): Promise<ScreeningResponse> {
  const resp = await fetch(`${API_BASE}/api/screening?run_date=${date}`);
  if (!resp.ok) {
    throw new Error(`fetch screening failed: ${resp.status}`);
  }
  return (await resp.json()) as ScreeningResponse;
}
