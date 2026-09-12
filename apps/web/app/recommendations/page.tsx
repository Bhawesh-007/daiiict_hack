"use client";

import { useState } from "react";
import Link from "next/link";
import Nav from "@/app/components/Nav";
import { api } from "@/lib/api-client";

const DEFAULT_ID = "10000000-0000-4000-8000-000000000003";

type Recommendation = {
  recommendation_id: string;
  intervention_id: string;
  intervention_name: string;
  short_description: string;
  intervention_type: string;
  circularity_dimension: string;
  source_name: string;
  baseline_emissions_kgco2e: string;
  contribution_percentage: string;
  rank: number;
  match_reasons: string[];
  required_conditions: string[];
  required_evidence: string[];
  impact_status: string;
  projected_emissions_kgco2e: string;
  carbon_reduction_kgco2e: string;
  reduction_percentage: string;
  implementation_cost_inr: string;
  annual_savings_inr: string;
  simple_payback_years: string | null;
  circularity_score: string;
  technical_feasibility_score: string;
  feasibility_score: string;
  feasibility_status: string;
  payback_status: string;
};

type RecommendationResponse = {
  profile_id: string;
  profile_version: number;
  recommendation_count: number;
  recommendations: Recommendation[];
  excluded_sources: Array<{ source_name?: string; reason: string }>;
  limitations: string[];
  impact_assumption_notice: string;
};

export default function RecommendationsPage() {
  const [assessmentId, setAssessmentId] = useState(DEFAULT_ID);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [message, setMessage] = useState("");

  async function loadRecommendations() {
    setMessage("Reading the latest finalized Layer 1 profile…");
    setResult(null);
    try {
      const response = await api<RecommendationResponse>(`/api/assessments/${assessmentId}/recommendations`);
      setResult(response);
      setMessage(`${response.recommendation_count} intervention candidate${response.recommendation_count === 1 ? "" : "s"} found.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Recommendations could not be loaded.");
    }
  }

  async function loadDemoRecommendations() {
    setMessage("Loading the synthetic Layer 1 profile…");
    setResult(null);
    try {
      const response = await api<RecommendationResponse>("/api/layer2/demo/recommendations");
      setResult(response);
      setMessage("Synthetic Layer 1 profile loaded and matched successfully.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The demo profile could not be loaded.");
    }
  }

  return <main><Nav />
    <div className="topbar"><div><p className="eyebrow">EMISSIONLENS · LAYER 2 PHASE 1</p><h1>Circular intervention candidates</h1><p>Read the finalized Layer 1 profile and review explainable intervention matches for its confirmed hotspots.</p></div><Link className="secondary-link" href="/calculations">Layer 1 calculations →</Link></div>
    <section className="control card"><label>Assessment ID<input aria-label="Assessment ID" value={assessmentId} onChange={event => setAssessmentId(event.target.value)} /></label><button onClick={loadRecommendations} disabled={!assessmentId.trim()}>Find candidates</button><button className="soft-button" onClick={loadDemoRecommendations}>Use synthetic profile</button></section>
    {message && <div className={message.includes("found") ? "notice success" : "notice"}>{message}</div>}
    {!result && <section className="empty card"><div className="empty-icon">↗</div><h2>Ready for the finalized profile</h2><p>Layer 2 reads the stored Layer 1 profile automatically. It does not ask for company, process, source or activity details again.</p></section>}
    {result && <>
      <section className="metrics"><div className="metric"><span>Candidate interventions</span><strong>{result.recommendation_count}</strong><small>Deterministic catalog matches</small></div><div className="metric"><span>Profile version</span><strong>v{result.profile_version}</strong><small>Trusted Layer 1 snapshot</small></div><div className="metric"><span>Excluded sources</span><strong>{result.excluded_sources.length}</strong><small>Not eligible or unmatched</small></div><div className="metric"><span>Impact model</span><strong>Deterministic</strong><small>Versioned catalog assumptions</small></div></section>
      <section className="recommendation-list">{result.recommendations.map(item => <article className="card recommendation-card" key={item.recommendation_id}><div className="recommendation-rank">{item.rank}</div><div className="recommendation-body"><div className="section-title"><div><p className="eyebrow">{item.intervention_id} · {item.intervention_type.replaceAll("_", " ")}</p><h2>{item.intervention_name}</h2></div><span className="pill">{item.circularity_dimension.replaceAll("_", " ")}</span></div><p>{item.short_description}</p><div className="recommendation-facts"><span><small>Source</small><strong>{item.source_name}</strong></span><span><small>Baseline</small><strong>{Number(item.baseline_emissions_kgco2e).toLocaleString()} kgCO₂e</strong></span><span><small>Contribution</small><strong>{Number(item.contribution_percentage).toFixed(1)}%</strong></span></div><div className="impact-grid"><span><small>Projected emissions</small><strong>{Number(item.projected_emissions_kgco2e).toLocaleString()} kgCO₂e</strong></span><span><small>Carbon reduction</small><strong>{Number(item.carbon_reduction_kgco2e).toLocaleString()} kgCO₂e ({Number(item.reduction_percentage).toFixed(1)}%)</strong></span><span><small>Implementation cost</small><strong>₹{Number(item.implementation_cost_inr).toLocaleString("en-IN")}</strong></span><span><small>Annual savings</small><strong>₹{Number(item.annual_savings_inr).toLocaleString("en-IN")}</strong></span><span><small>Simple payback</small><strong>{item.simple_payback_years ? `${Number(item.simple_payback_years).toFixed(1)} years` : "Unavailable"}</strong></span><span><small>Feasibility</small><strong>{item.feasibility_status.replaceAll("_", " ")}</strong></span></div><div className="score-row"><span>Circularity <b>{Number(item.circularity_score).toFixed(0)}/100</b></span><span>Technical fit <b>{Number(item.technical_feasibility_score).toFixed(0)}/100</b></span><span>Overall feasibility <b>{Number(item.feasibility_score).toFixed(0)}/100</b></span></div><div className="recommendation-columns"><div><small>Why it matched</small><ul>{item.match_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div><div><small>Required before deployment</small><ul>{item.required_conditions.map(condition => <li key={condition}>{condition}</li>)}</ul></div></div><p className="recommendation-status">{item.impact_status.replaceAll("_", " ")} · Payback {item.payback_status.replaceAll("_", " ")}</p></div></article>)}</section>
      {result.excluded_sources.length > 0 && <section className="card result-footer"><h2>Sources held back</h2>{result.excluded_sources.map(item => <p className="warning-text" key={`${item.source_name}-${item.reason}`}>{item.source_name || "Source"}: {item.reason.replaceAll("_", " ")}</p>)}</section>}
      <section className="card result-footer"><h2>Phase 2 assumptions</h2><p>{result.impact_assumption_notice}</p>{result.limitations.map(item => <p key={item}>{item}</p>)}</section>
    </>}
  </main>;
}
