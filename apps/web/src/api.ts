import type { AnalysisResponse, EtfResponse, ScreeningResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function fetchDates(): Promise<string[]> {
  const resp = await fetch(`${API_BASE}/screening/dates`);
  if (!resp.ok) {
    throw new Error(`fetch dates failed: ${resp.status}`);
  }
  const json = (await resp.json()) as { dates: string[] };
  return json.dates ?? [];
}

export async function fetchScreening(date: string): Promise<ScreeningResponse> {
  const resp = await fetch(`${API_BASE}/screening?run_date=${date}`);
  if (!resp.ok) {
    throw new Error(`fetch screening failed: ${resp.status}`);
  }
  return (await resp.json()) as ScreeningResponse;
}

export async function fetchEtfDates(): Promise<string[]> {
  const resp = await fetch(`${API_BASE}/etf/dates`);
  if (!resp.ok) {
    throw new Error(`fetch etf dates failed: ${resp.status}`);
  }
  const json = (await resp.json()) as { dates: string[] };
  return json.dates ?? [];
}

export async function fetchEtf(date: string): Promise<EtfResponse> {
  const resp = await fetch(`${API_BASE}/etf?run_date=${date}`);
  if (!resp.ok) {
    throw new Error(`fetch etf failed: ${resp.status}`);
  }
  return (await resp.json()) as EtfResponse;
}

export async function fetchAnalysisDates(): Promise<string[]> {
  const resp = await fetch(`${API_BASE}/analysis/dates`);
  if (!resp.ok) {
    throw new Error(`fetch analysis dates failed: ${resp.status}`);
  }
  const json = (await resp.json()) as { dates: string[] };
  return json.dates ?? [];
}

export async function fetchAnalysis(date: string): Promise<AnalysisResponse> {
  const resp = await fetch(`${API_BASE}/analysis?run_date=${date}`);
  if (!resp.ok) {
    throw new Error(`fetch analysis failed: ${resp.status}`);
  }
  return (await resp.json()) as AnalysisResponse;
}
