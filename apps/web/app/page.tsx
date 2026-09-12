"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/app/components/Nav";
import { api } from "@/lib/api-client";

const DEMO_ID = "10000000-0000-4000-8000-000000000003";
type Assessment = { id: string; industry_name?: string; industry_code?: string; industry_template_key?: string; industry_template_version?: string; reporting_period_start?: string; reporting_period_end?: string; organizational_boundary?: string; operational_boundary?: string; status?: string; facility?: { name?: string; location?: string }; company?: { name?: string; msme_category?: string; address?: string } };
const formatDate = (value?: string) => value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not provided";

export default function AssessmentLanding() {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { api<Assessment>(`/api/assessments/${DEMO_ID}`).then(setAssessment).catch(e => setError(e instanceof Error ? e.message : "Assessment could not be loaded.")).finally(() => setLoading(false)); }, []);
  return <main><Nav /><section className="landing-hero"><div><p className="eyebrow">Operational carbon inventory</p><h1>Know where your emissions come from.</h1><p className="hero-copy">Map the facility, verify each source, and calculate a defensible emissions baseline.</p></div><div className="hero-badge"><span>●</span><small>Assessment status</small><strong>{assessment?.status || "Loading"}</strong></div></section>
    {loading && <section className="card loading-card"><div className="spinner" /><p>Loading your assessment details…</p></section>}
    {error && <section className="card error-card"><h2>We could not load this assessment</h2><p>{error}</p><button onClick={() => window.location.reload()}>Try again</button></section>}
    {assessment && <><section className="profile-grid"><article className="card profile-main"><div className="profile-heading"><div className="company-mark">{(assessment.company?.name || "C").slice(0, 1).toUpperCase()}</div><div><p className="eyebrow">Company</p><h2>{assessment.company?.name || "Company profile"}</h2><p>{assessment.company?.msme_category || "MSME"} · {assessment.company?.address || "Location not provided"}</p></div></div><div className="facility-strip"><span>⌂</span><div><small>Facility</small><strong>{assessment.facility?.name || "Facility profile"}</strong><p>{assessment.facility?.location || "Location not provided"}</p></div></div></article><article className="card details-card"><p className="eyebrow">Assessment details</p><div className="detail-row"><span>Industry</span><strong>{assessment.industry_name || assessment.industry_code || "Not provided"}</strong></div><div className="detail-row"><span>Reporting period</span><strong>{formatDate(assessment.reporting_period_start)} – {formatDate(assessment.reporting_period_end)}</strong></div><div className="detail-row"><span>Boundary</span><strong>{assessment.operational_boundary || assessment.organizational_boundary || "Not provided"}</strong></div><div className="detail-row"><span>Template</span><strong>{assessment.industry_template_key || "Not selected"} <em>v{assessment.industry_template_version || "—"}</em></strong></div></article></section><section className="card start-card"><div><p className="eyebrow">Next</p><h2>Build the facility map</h2><p>Load an editable process template, then adjust it to match the real operation.</p></div><Link className="primary-cta" href="/template">Open starter map <span>→</span></Link></section></>}
  </main>;
}
