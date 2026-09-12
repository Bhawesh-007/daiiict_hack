"use client";

import Link from "next/link";
import { useState } from "react";
import Nav from "@/app/components/Nav";
import { api, API_BASE } from "@/lib/api-client";

const DEFAULT_ID = "10000000-0000-4000-8000-000000000003";

type Candidate = {
  id: string;
  source_name: string;
  source_key: string;
  reason?: string;
  origin: string;
  status: string;
  suggested_scope?: string;
  evidence_json?: { candidate_count?: number; evidence?: Array<{ origin?: string; reason?: string; process_step_id?: string; equipment_id?: string }> };
};

type Process = { id: string; name: string; equipment?: Array<{ name: string }> };
type Inventory = { id: string; source_name: string; status: string; scope?: string };
type Checklist = { items?: Array<{ source_key?: string; label?: string; source_name?: string; status: string; reason?: string; metadata?: { evidence_sources?: string[] } }> };
type Assessment = { industry_name?: string; industry_code?: string; industry_template_key?: string; reporting_period_start?: string; reporting_period_end?: string; status?: string; company?: { name?: string; msme_category?: string; address?: string }; facility?: { name?: string; location?: string } };

export default function WorkflowPage() {
  const [assessmentId, setAssessmentId] = useState(DEFAULT_ID);
  const [message, setMessage] = useState("Select an action to update this assessment.");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [processes, setProcesses] = useState<Process[]>([]);
  const [inventory, setInventory] = useState<Inventory[]>([]);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [showExcludedChecklistSources, setShowExcludedChecklistSources] = useState(false);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [activeKpi, setActiveKpi] = useState("processes");

  async function action(label: string, work: () => Promise<void>) {
    setMessage(`${label}…`);
    try {
      await work();
      setMessage(`${label} complete.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "This step could not be completed.");
    }
  }

  async function review(candidate: Candidate, status: string) {
    await action(`${status === "CONFIRMED" ? "Confirming" : "Updating"} ${candidate.source_name}`, async () => {
      await api(`/api/assessments/${assessmentId}/candidates/${candidate.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          status,
          confirmation_note: status === "NOT_APPLICABLE" ? "Not relevant to this facility." : undefined,
          confirmed_by: status === "CONFIRMED" ? "Prototype user" : undefined,
          confirmed_at: status === "CONFIRMED" ? new Date().toISOString() : undefined,
        }),
      });
      setCandidates(current => current.filter(item => item.id !== candidate.id));
      const items = await api<Inventory[]>(`/api/assessments/${assessmentId}/inventory`);
      setInventory(items);
      setChecklist(await api<Checklist>(`/api/assessments/${assessmentId}/checklist`));
    });
  }

  async function buildDemoProfile() {
    await action("Building complete demonstration profile", async () => {
      await api(`/api/assessments/${assessmentId}/load-template`, { method: "POST", body: JSON.stringify({ template_key: "industry-food-processing-v1" }) });
      await api(`/api/assessments/${assessmentId}/identify`, { method: "POST", body: JSON.stringify({ include_ml: true }) });
      const found = await api<Candidate[]>(`/api/assessments/${assessmentId}/candidates`);
      const supported = new Set(["purchased_grid_electricity", "stationary_fuel_combustion", "refrigerant_fugitive_emissions", "waste_generated_in_operations", "downstream_transportation"]);
      for (const candidate of found.filter(item => supported.has(item.source_key))) {
        await api(`/api/assessments/${assessmentId}/candidates/${candidate.id}/review`, { method: "POST", body: JSON.stringify({ status: "CONFIRMED", confirmed_by: "Prototype demo", confirmed_at: new Date().toISOString() }) });
      }
      const csv = [
        "source_key,quantity,unit_code,period_start,period_end,evidence_reference,notes",
        "purchased_grid_electricity,185000,kWh,2025-04-01,2026-03-31,demo-utility-bill.csv,Annual purchased electricity",
        "stationary_fuel_combustion,12500,litre,2025-04-01,2026-03-31,demo-diesel-log.csv,Boiler and generator diesel",
        "refrigerant_fugitive_emissions,18,kg,2025-04-01,2026-03-31,demo-cold-room-service.csv,R-134a refill treated as release for demo",
        "waste_generated_in_operations,26000,kg,2025-04-01,2026-03-31,demo-waste-manifest.csv,Organic waste to landfill",
        "downstream_transportation,96000,tonne_km,2025-04-01,2026-03-31,demo-dispatch-log.csv,Third-party road freight",
      ].join("\n");
      const response = await fetch(`${API_BASE}/api/assessments/${assessmentId}/import-activity-file?filename=prototype-demo.csv`, { method: "POST", headers: { "Content-Type": "text/csv" }, body: csv });
      const imported = await response.json();
      if (!response.ok) throw new Error(imported.detail || "Demo activity import failed");
      await api("/api/emission-factors/seed-demo", { method: "POST" });
      await api(`/api/assessments/${assessmentId}/calculate`, { method: "POST" });
      setInventory(await api<Inventory[]>(`/api/assessments/${assessmentId}/inventory`));
      window.location.href = "/calculations";
    });
  }

  const confirmed = inventory.filter(item => item.status === "CONFIRMED").length;
  const gaps = checklist?.items?.filter(item => item.status === "MISSING_INFORMATION").length ?? 0;

  return <main><Nav />
    <div className="topbar"><div><p className="eyebrow">Source identification</p><h1>Assessment workspace</h1><p>Review facility evidence, identify possible sources, and record each decision.</p></div><Link className="secondary-link" href="/calculations">View emissions →</Link></div>
    <section className="control card"><label>Assessment ID<input value={assessmentId} onChange={event => setAssessmentId(event.target.value)} /></label></section>
    <div className="notice">{message}</div>
    <section className="workflow-steps">
      <button className="primary-workflow" onClick={buildDemoProfile}><b>↗</b><span><strong>Prepare demo assessment</strong><small>Load sample processes, review supported sources, import activity data, and calculate the result.</small></span></button>
      <button onClick={() => action("Loading your assessment", async () => { setAssessment(await api<Assessment>(`/api/assessments/${assessmentId}`)); })}><b>1</b><span><strong>View assessment</strong></span></button>
      <button onClick={() => action("Loading industry process suggestions", async () => { setProcesses(await api<Process[]>(`/api/assessments/${assessmentId}/load-template`, { method: "POST", body: JSON.stringify({ template_key: "industry-food-processing-v1" }) })); })}><b>2</b><span><strong>Load industry starter map</strong></span></button>
      <button onClick={() => action("Loading process map", async () => { setProcesses(await api<Process[]>(`/api/assessments/${assessmentId}/processes`)); })}><b>3</b><span><strong>View process map</strong></span></button>
      <button onClick={() => action("Finding possible emission sources", async () => { await api(`/api/assessments/${assessmentId}/identify`, { method: "POST", body: JSON.stringify({ include_ml: true }) }); setCandidates(await api<Candidate[]>(`/api/assessments/${assessmentId}/candidates`)); })}><b>4</b><span><strong>Find possible sources</strong></span></button>
      <button onClick={() => action("Checking source coverage", async () => { setChecklist(await api<Checklist>(`/api/assessments/${assessmentId}/checklist`)); })}><b>5</b><span><strong>Check source coverage</strong></span></button>
      <button onClick={() => action("Loading reviewed sources", async () => { setInventory(await api<Inventory[]>(`/api/assessments/${assessmentId}/inventory`)); })}><b>6</b><span><strong>Review confirmed sources</strong></span></button>
    </section>
    {assessment && <section className="card workflow-assessment"><div className="section-title"><div><p className="eyebrow">ASSESSMENT DETAILS</p><h2>{assessment.company?.name || "Company assessment"}</h2></div><span className="pill">{assessment.status || "DRAFT"}</span></div><div className="assessment-facts"><div><small>Facility</small><strong>{assessment.facility?.name || "Not provided"}</strong><span>{assessment.facility?.location || "Location not provided"}</span></div><div><small>Industry</small><strong>{assessment.industry_name || assessment.industry_code || "Not provided"}</strong><span>{assessment.industry_template_key || "Template not selected"}</span></div><div><small>Reporting period</small><strong>{assessment.reporting_period_start ? new Date(assessment.reporting_period_start).toLocaleDateString("en-IN") : "Not provided"} – {assessment.reporting_period_end ? new Date(assessment.reporting_period_end).toLocaleDateString("en-IN") : "Not provided"}</strong><span>Assessment boundary</span></div></div></section>}
    {processes.length > 0 && <section className="card"><h2 className="panel-title">Process map</h2><div className="chip-list">{processes.map(process => <span className="chip" key={process.id}>{process.name}{process.equipment?.length ? ` · ${process.equipment.length} equipment` : ""}</span>)}</div></section>}
    {checklist?.items && <ChecklistPanel checklist={checklist} showExcluded={showExcludedChecklistSources} onToggleExcluded={() => setShowExcludedChecklistSources(value => !value)} />}
    {candidates.length > 0 && <section className="card review-panel"><div className="section-title"><div><p className="eyebrow">SOURCE REVIEW</p><h2>Relevant sources to review</h2></div><span className="pill">{candidates.length} unique categories</span></div>{candidates.map(candidate => <article className="candidate" key={candidate.id}><div><h3>{candidate.source_name}</h3><p>{candidate.reason || "Suggested for review."}</p><small>{candidate.origin} suggestion · {candidate.suggested_scope || "Scope to review"}{candidate.evidence_json?.candidate_count && candidate.evidence_json.candidate_count > 1 ? ` · ${candidate.evidence_json.candidate_count} evidence records merged` : ""}</small>{candidate.evidence_json?.evidence?.slice(0, 4).map((evidence, index) => <em className="candidate-evidence" key={`${candidate.id}-evidence-${index}`}>{evidence.reason || `${evidence.origin || "Evidence"} context`}</em>)}</div><div className="candidate-actions"><button onClick={() => review(candidate, "CONFIRMED")}>Confirm source</button><button className="soft-button" onClick={() => review(candidate, "MISSING_INFORMATION")}>Need info</button><button className="text-button" onClick={() => review(candidate, "NOT_APPLICABLE")}>Not applicable</button></div></article>)}</section>}
    {inventory.length > 0 && <section className="card workflow-data-panel"><div className="section-title"><div><p className="eyebrow">REVIEWED INVENTORY</p><h2>Source inventory</h2></div><span className="pill">{confirmed} confirmed</span></div><div className="inventory-grid">{inventory.map(item => <div className="inventory-item" key={item.id}><strong>{item.source_name}</strong><span>{item.status.replaceAll("_", " ")}</span></div>)}</div></section>}
    <section className="next-steps"><Link className="next-step" href="/"><span>7</span><div><strong>Add activity data</strong></div>→</Link><button className="next-step" onClick={() => action("Loading demonstration emission factors", async () => { await api("/api/emission-factors/seed-demo", { method: "POST" }); })}><span>8</span><div><strong>Prepare emission factors</strong></div>→</button><Link className="next-step" href="/calculations"><span>9</span><div><strong>Calculate emissions</strong></div>→</Link></section>
    <section className="metrics workspace-metrics"><Metric label="Processes mapped" value={String(processes.length)} active={activeKpi === "processes"} onClick={() => setActiveKpi("processes")} /><Metric label="Suggestions to review" value={String(candidates.length)} active={activeKpi === "suggestions"} onClick={() => setActiveKpi("suggestions")} /><Metric label="Confirmed sources" value={String(confirmed)} active={activeKpi === "confirmed"} onClick={() => setActiveKpi("confirmed")} /><Metric label="Information gaps" value={String(gaps)} active={activeKpi === "gaps"} onClick={() => setActiveKpi("gaps")} /></section>
    <section className="card kpi-detail"><p className="eyebrow">SELECTED KPI</p><h2>{activeKpi === "processes" ? "Processes mapped" : activeKpi === "suggestions" ? "Suggestions to review" : activeKpi === "confirmed" ? "Confirmed sources" : "Information gaps"}</h2><p>{activeKpi === "processes" ? (processes.length ? `The assessment currently contains ${processes.length} saved process step${processes.length === 1 ? "" : "s"}. Review equipment and flows from the process map.` : "No process steps have been loaded yet. Use Load industry starter map to begin.") : activeKpi === "suggestions" ? (candidates.length ? `${candidates.length} source suggestion${candidates.length === 1 ? " is" : "s are"} waiting for a user decision above.` : "No source suggestions are waiting for review.") : activeKpi === "confirmed" ? (confirmed ? `${confirmed} source${confirmed === 1 ? " is" : "s are"} confirmed and eligible for activity data.` : "No sources are confirmed yet. Review the suggestions above.") : (gaps ? `${gaps} checklist item${gaps === 1 ? " remains" : "s remain"} marked as missing information. Resolve these before treating the inventory as complete.` : "No missing-information gaps are currently recorded.")}</p></section>
  </main>;
}

function ChecklistPanel({ checklist, showExcluded, onToggleExcluded }: { checklist: Checklist; showExcluded: boolean; onToggleExcluded: () => void }) {
  const items = checklist.items || [];
  const relevant = items.filter(item => item.status !== "NOT_APPLICABLE");
  const excluded = items.filter(item => item.status === "NOT_APPLICABLE");
  const visible = showExcluded ? [...relevant, ...excluded] : relevant;
  return <section className="card workflow-data-panel"><div className="section-title"><div><p className="eyebrow">SOURCE COVERAGE</p><h2>Relevant sources</h2><p className="muted">Master coverage is evaluated against this assessment’s process map, equipment, reviews and activity data.</p></div><span className="pill">{relevant.length} relevant</span></div><div className="checklist-grid">{visible.map((item, index) => <article className="checklist-item" key={item.source_key || index}><span className={`status-dot ${item.status.toLowerCase()}`} /><div><strong>{item.label || item.source_name || item.source_key || "Source family"}</strong><small>{item.status.replaceAll("_", " ")}</small><p>{item.reason}</p>{item.metadata?.evidence_sources?.length ? <em>Evidence: {item.metadata.evidence_sources.join(", ")}</em> : null}</div></article>)}</div>{excluded.length > 0 && <button className="text-button checklist-toggle" onClick={onToggleExcluded}>{showExcluded ? "Hide sources marked not applicable" : `Show ${excluded.length} source${excluded.length === 1 ? "" : "s"} marked not applicable`}</button>}</section>;
}

function Metric({ label, value, active, onClick }: { label: string; value: string; active?: boolean; onClick?: () => void }) {
  return <button type="button" className={`metric metric-button${active ? " active" : ""}`} onClick={onClick}><span>{label}</span><strong>{value}</strong><small>View details →</small></button>;
}
