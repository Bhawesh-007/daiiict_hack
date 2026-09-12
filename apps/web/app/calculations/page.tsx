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

type AggregateItem = { key: string; label: string; value: number; percentage: number };

const COLORS = ["#6288ff", "#46c6d8", "#ff9e45", "#a879ff", "#ff7788", "#88a9ff", "#6fd3a4"];
const pretty = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const kg = (value: number) => `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} kgCO₂e`;
const tonnes = (value: number) => `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e`;

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

  const total = Number(result?.total_emissions_kgco2e || 0);
  const lines = result?.summary?.line_items?.length ? result.summary.line_items : result?.lines || [];
  const charts = useMemo(() => ({
    sources: aggregate(lines, line => line.source_name, total),
    scopes: aggregate(lines, line => line.scope, total),
    categories: aggregate(lines, line => line.source_category, total),
    processes: aggregate(lines, line => line.process_name, total),
  }), [lines, total]);
  const largest = charts.sources[0];

  return <main><Nav />
    <div className="topbar"><div><p className="eyebrow">Calculation results</p><h1>Emissions baseline</h1><p>Every chart below is derived from the quantified calculation lines returned by the backend.</p></div><Link className="secondary-link" href="/workflow">Source review →</Link></div>
    <section className="control card"><label>Assessment ID<input aria-label="Assessment ID" value={assessmentId} onChange={event => setAssessmentId(event.target.value)} /></label><button onClick={calculate} disabled={!assessmentId.trim()}>Run calculation</button></section>
    {message && <div className={message.includes("complete") ? "notice success" : "notice"}>{message}</div>}
    {!result && <section className="empty card"><div className="empty-icon">∑</div><h2>Ready to calculate</h2><p>Confirm source inventory and save activity data first. The calculation engine will normalize compatible units, resolve active factors, and keep unresolved lines visible as gaps.</p></section>}
    {result && <>
      <section className="metrics"><Metric label="Total emissions" value={kg(total)} note={`${tonnes(total)} readable equivalent`} /><Metric label="Calculated sources" value={String(charts.sources.length)} note={`${lines.length} quantified lines`} /><Metric label="Largest contributor" value={largest?.label || "No source calculated"} note={largest ? `${largest.percentage.toFixed(1)}% of quantified total` : "No quantified source"} /><Metric label="Run status" value={result.status} note={result.summary?.is_partial ? "Partial total" : "Complete quantified total"} /></section>
      <section className="dashboard-grid"><div className="card"><DonutChart title="Emissions by Source" items={charts.sources} large /></div><div className="card"><DonutChart title="Emissions by Scope" items={charts.scopes} /></div></section>
      <section className="chart-grid"><div className="card"><BarChart title="Emissions by Category" items={charts.categories} /></div><div className="card"><BarChart title="Emissions by Process" items={charts.processes} unavailableMessage="Process-level breakdown is unavailable for this calculation." /></div></section>
      <section className="card insight"><div><p className="eyebrow">Largest contributor</p><h2>{largest?.label || "No source calculated"}</h2><p>{largest ? `${kg(largest.value)} · ${largest.percentage.toFixed(1)}% of quantified emissions.` : "Add confirmed activity data to rank emission sources."}</p></div><div className="insight-mark">↗</div></section>
      <section className="card source-table-card"><div className="section-title"><div><p className="eyebrow">QUANTIFIED SOURCES</p><h2>Top emission sources</h2></div><span className="pill">{charts.sources.length} sources</span></div><div className="source-table"><div className="source-table-row source-table-head"><span>Rank</span><span>Source</span><span>CO₂e</span><span>Contribution</span></div>{charts.sources.map((item, index) => <div className="source-table-row" key={item.key}><span>{index + 1}</span><strong>{item.label}</strong><span>{kg(item.value)}</span><b>{item.percentage.toFixed(1)}%</b></div>)}</div></section>
      <section className="card result-footer"><h2>What needs attention</h2>{(result.summary?.is_partial || result.summary?.unquantified_sources?.length) ? <p className="warning-text">Some sources remain unquantified. Review the activity and factor gaps before treating the ranking as complete.</p> : <p className="success-text">All available confirmed activity lines were calculated successfully.</p>}<p className="run-id">Run ID: {result.calculation_run_id}</p></section>
    </>}
  </main>;
}
