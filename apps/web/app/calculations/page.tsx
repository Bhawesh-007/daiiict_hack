"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import Nav from "@/app/components/Nav";

type CalculationLine = {
  source_name?: string | null;
  source_category?: string | null;
  scope?: string | null;
  process_name?: string | null;
  emissions_kgco2e?: string | number | null;
};

type Summary = {
  line_items?: CalculationLine[];
  is_partial?: boolean;
  unquantified_sources?: string[];
};

type CalculationResponse = {
  calculation_run_id: string;
  status: string;
  total_emissions_kgco2e: string;
  total_emissions_tco2e?: string;
  summary: Summary;
  lines: CalculationLine[];
};

type FinalProfileResponse = {
  profile_id: string;
  profile_version: number;
  baseline_emissions_kgco2e: string;
  profile_status: string;
};

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

function aggregate(lines: CalculationLine[], getKey: (line: CalculationLine) => string | null | undefined, total: number): AggregateItem[] {
  const values = new Map<string, { label: string; value: number }>();
  for (const line of lines) {
    const rawKey = getKey(line);
    const value = Number(line.emissions_kgco2e ?? 0);
    if (!rawKey || !Number.isFinite(value) || value <= 0) continue;
    const key = rawKey.trim();
    const current = values.get(key) || { label: key, value: 0 };
    current.value += value;
    values.set(key, current);
  }
  return Array.from(values.entries())
    .map(([key, item]) => ({ key, label: key.includes("_") ? pretty(item.label) : item.label, value: item.value, percentage: total > 0 ? (item.value / total) * 100 : 0 }))
    .sort((a, b) => b.value - a.value);
}

function collapseSmallSlices(items: AggregateItem[], maxSlices = 6): AggregateItem[] {
  if (items.length <= maxSlices) return items;
  const visible = items.slice(0, maxSlices);
  const otherValue = items.slice(maxSlices).reduce((sum, item) => sum + item.value, 0);
  const total = items.reduce((sum, item) => sum + item.value, 0);
  return [...visible, { key: "other", label: "Other", value: otherValue, percentage: total ? (otherValue / total) * 100 : 0 }];
}

function DonutChart({ title, items, large = false }: { title: string; items: AggregateItem[]; large?: boolean }) {
  const visible = collapseSmallSlices(items);
  const total = visible.reduce((sum, item) => sum + item.value, 0);
  const radius = large ? 82 : 65;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return <div className={`visual-card ${large ? "visual-card-large" : ""}`}><h3>{title}</h3>{visible.length ? <div className="donut-layout"><div className={`donut ${large ? "donut-large" : ""}`}><svg viewBox="0 0 220 220" role="img" aria-label={title}><circle className="donut-track" cx="110" cy="110" r={radius} />{visible.map((item, index) => { const length = total ? (item.value / total) * circumference : 0; const circle = <circle key={item.key} cx="110" cy="110" r={radius} fill="none" stroke={COLORS[index % COLORS.length]} strokeWidth={large ? 26 : 22} strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} transform="rotate(-90 110 110)"><title>{`${item.label}: ${kg(item.value)} · ${item.percentage.toFixed(1)}%`}</title></circle>; offset += length; return circle; })}</svg><div className="donut-center"><strong>{(total / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong><small>tCO₂e</small></div></div><div className="legend">{visible.map((item, index) => <div className="legend-row" key={item.key}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{item.label}</span><b>{item.percentage.toFixed(1)}%</b></div>)}</div></div> : <p className="muted">No quantified data yet.</p>}</div>;
}

function BarChart({ title, items, unavailableMessage }: { title: string; items: AggregateItem[]; unavailableMessage?: string }) {
  const max = items[0]?.value || 0;
  return <div className="visual-card bar-chart-card"><h3>{title}</h3>{items.length ? <div className="bars">{items.map(item => <div className="bar-row" key={item.key}><div className="bar-label"><span>{item.label}</span><b>{tonnes(item.value)}</b></div><div className="track"><div className="bar" style={{ width: `${max ? (item.value / max) * 100 : 0}%` }} /></div><small>{item.percentage.toFixed(1)}% of quantified emissions</small></div>)}</div> : <p className="muted">{unavailableMessage || "No quantified data yet."}</p>}</div>;
}

export default function CalculationsPage() {
  const [assessmentId, setAssessmentId] = useState("10000000-0000-4000-8000-000000000003");
  const [result, setResult] = useState<CalculationResponse | null>(null);
  const [profile, setProfile] = useState<FinalProfileResponse | null>(null);
  const [message, setMessage] = useState("");

  async function calculate() {
    setMessage("Running deterministic calculation…");
    setResult(null);
    try {
      const response = await api<CalculationResponse>(`/api/assessments/${assessmentId}/calculate`, { method: "POST" });
      setResult(response);
      setMessage("Calculation complete. This is a quantified prototype result.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Calculation could not be completed.");
    }
  }

  async function finalize() {
    setMessage("Finalizing the Layer 1 profile…");
    try {
      const response = await api<FinalProfileResponse>(`/api/assessments/${assessmentId}/finalize`, { method: "POST" });
      setProfile(response);
      setMessage(`Layer 1 profile finalized as version ${response.profile_version}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The Layer 1 profile could not be finalized.");
    }
  }

  const summary = result?.summary;
  const sources = summary?.by_source ?? [];

  return <main><Nav />
    <div className="topbar"><div><p className="eyebrow">Calculation results</p><h1>Emissions baseline</h1><p>Every chart below is derived from the quantified calculation lines returned by the backend.</p></div><Link className="secondary-link" href="/workflow">Source review →</Link></div>
    <section className="control card"><label>Assessment ID<input aria-label="Assessment ID" value={assessmentId} onChange={event => setAssessmentId(event.target.value)} /></label><button onClick={calculate} disabled={!assessmentId.trim()}>Run calculation</button></section>
    {message && <div className={message.includes("complete") ? "notice success" : "notice"}>{message}</div>}
    {!result && <section className="empty card"><div className="empty-icon">∑</div><h2>Ready to calculate</h2><p>Confirm source inventory and save activity data first. The calculation engine will normalize compatible units, resolve active factors, and keep unresolved lines visible as gaps.</p></section>}
    {result && <>
      <section className="metrics"><Metric label="Total quantified emissions" value={`${Number(result.total_emissions_kgco2e).toLocaleString()} kgCO₂e`} note={summary?.total_status === "PARTIAL" ? "Partial total" : "Complete quantified total"} /><Metric label="Calculated lines" value={String(summary?.quantified_line_count ?? result.lines.length)} /><Metric label="Source hotspots" value={String(summary?.by_source?.length ?? 0)} /><Metric label="Run status" value={result.status} /></section>
      <section className="chart-grid"><div className="card"><PieChart title="Emissions by source" items={sources} /></div><div className="card"><PieChart title="Emissions by scope" items={summary?.by_scope ?? []} /></div><div className="card"><PieChart title="Emissions by category" items={summary?.by_category ?? []} /></div><div className="card"><PieChart title="Emissions by process" items={summary?.by_process ?? []} /></div></section>
      <section className="card insight"><div><p className="eyebrow">INSIGHT</p><h2>Where to focus first</h2><p>{sources[0] ? `${sources[0].label || sources[0].key} is the largest quantified source at ${Number(sources[0].percentage).toFixed(1)}% of the current total.` : "Add confirmed activity data to reveal the largest quantified sources."}</p></div><div className="insight-mark">↗</div></section>
      <section className="card result-footer"><h2>What needs attention</h2>{(summary?.total_status === "PARTIAL" || (result.summary as Summary & { unquantified_sources?: string[] })?.unquantified_sources?.length) ? <p className="warning-text">Some sources remain unquantified. Review the activity and factor gaps before treating the ranking as complete.</p> : <p className="success-text">All available confirmed activity lines were calculated successfully.</p>}<p className="run-id">Run ID: {result.calculation_run_id}</p><button onClick={finalize}>Finalize Layer 1 profile</button>{profile && <p className="success-text">Profile {profile.profile_id} · version {profile.profile_version} is ready for Layer 2.</p>}</section>
    </>}
  </main>;
}
