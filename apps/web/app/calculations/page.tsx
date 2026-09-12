"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import Nav from "@/app/components/Nav";

type Summary = {
  quantified_total_emissions_kgco2e?: string;
  total_status?: string;
  quantified_line_count?: number;
  emissions_intensity_kgco2e_per_production_unit?: string | null;
  by_scope?: Array<{ key: string; emissions_kgco2e: string; percentage: string }>;
  by_source?: Array<{ key: string; label?: string; emissions_kgco2e: string; percentage: string }>;
  by_category?: Array<{ key: string; label?: string; emissions_kgco2e: string; percentage: string }>;
  by_process?: Array<{ key: string; label?: string; emissions_kgco2e: string; percentage: string }>;
};

type CalculationResponse = {
  calculation_run_id: string;
  status: string;
  total_emissions_kgco2e: string;
  summary: Summary;
  lines: Array<{ id: string; emissions_kgco2e: string; source_category?: string; scope?: string }>;
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

const COLORS = ["#176b45", "#35a46b", "#e3a93b", "#4c78a8", "#b85c8a", "#7c62a8"];

function PieChart({ title, items }: { title: string; items: Array<{ key: string; label?: string; percentage: string }> }) {
  const visible = items.filter(item => Number(item.percentage) > 0);
  let cursor = 0;
  const stops = visible.map((item, index) => {
    const start = cursor; cursor += Number(item.percentage);
    return `${COLORS[index % COLORS.length]} ${start}% ${cursor}%`;
  });
  return <div className="pie-card"><h3>{title}</h3>{visible.length ? <div className="pie-layout"><div className="pie" style={{ background: `conic-gradient(${stops.join(", ")})` }}><div className="pie-hole"><strong>{Math.round(visible.reduce((sum, item) => sum + Number(item.percentage), 0))}%</strong><small>quantified</small></div></div><div className="legend">{visible.map((item, index) => <div className="legend-row" key={item.key}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{item.label || item.key}</span><b>{Number(item.percentage).toFixed(1)}%</b></div>)}</div></div> : <p className="muted">No quantified data yet.</p>}</div>;
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
    <div className="topbar"><div><p className="eyebrow">EMISSIONLENS · LAYER 1</p><h1>Calculation summary</h1><p>Turn reviewed activity data into a transparent, versioned emissions snapshot.</p></div><Link className="secondary-link" href="/">Activity data →</Link></div>
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
