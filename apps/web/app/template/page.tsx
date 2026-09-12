"use client";

import { useState } from "react";
import Link from "next/link";
import Nav from "@/app/components/Nav";
import { api } from "@/lib/api-client";

const ASSESSMENT_ID = "10000000-0000-4000-8000-000000000003";
const TEMPLATE_KEY = "industry-food-processing-v1";

type Process = {
  id: string;
  name: string;
  sequence_order?: number;
  status?: string;
  equipment?: Array<{ id?: string; name: string; status?: string }>;
  inputs?: Array<{ item_name?: string; flow_type?: string }>;
  outputs?: Array<{ item_name?: string; flow_type?: string }>;
};

export default function TemplatePage() {
  const [processes, setProcesses] = useState<Process[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("This starter map is editable and does not confirm what happens at your facility.");

  async function loadTemplate() {
    setLoading(true);
    setMessage("Loading industry starter map…");
    try {
      const result = await api<Process[]>(`/api/assessments/${ASSESSMENT_ID}/load-template`, {
        method: "POST",
        body: JSON.stringify({ template_key: TEMPLATE_KEY }),
      });
      setProcesses(result);
      setMessage(`${result.length} editable process suggestions loaded. Review them before continuing.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The starter map could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  return <main>
    <Nav />
    <div className="topbar"><div><p className="eyebrow">02 / Process template</p><h1>Start with likely processes</h1><p>Use the industry template as a draft. Keep only what matches the facility.</p></div><Link className="secondary-link" href="/">← Overview</Link></div>
    <section className="card template-intro"><div className="template-icon">02</div><div><p className="eyebrow">Food processing / v1.0.0</p><h2>Starter process map</h2><p>Common production, storage, packaging, and support activities.</p></div><button onClick={loadTemplate} disabled={loading}>{loading ? "Loading…" : processes.length ? "Reload map" : "Load map"}</button></section>
    <div className="notice success">{message}</div>
    {processes.length > 0 && <section className="template-list"><div className="section-title"><div><p className="eyebrow">EDITABLE SUGGESTIONS</p><h2>Suggested process flow</h2></div><span className="pill">Not confirmed</span></div>{processes.map((process, index) => <article className="card template-process" key={process.id}><div className="process-number">{index + 1}</div><div className="process-content"><div className="process-title"><div><h3>{process.name}</h3><span className="suggested-tag">Suggested starting point</span></div><button className="soft-button" type="button">Edit later</button></div>{process.equipment && process.equipment.length > 0 && <div className="template-detail"><small>Equipment to review</small><div className="chip-list">{process.equipment.map(item => <span className="chip" key={item.id || item.name}>{item.name}</span>)}</div></div>}</div></article>)}</section>}
    <section className="card template-next"><div><p className="eyebrow">NEXT STEP</p><h2>Map what actually exists</h2><p>Save the process order, equipment and material or energy flows that your team confirms.</p></div><Link className="primary-cta" href="/processes">Continue to process mapping <span>→</span></Link></section>
  </main>;
}
