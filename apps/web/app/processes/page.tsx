"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/app/components/Nav";
import { api } from "@/lib/api-client";

const ASSESSMENT_ID = "10000000-0000-4000-8000-000000000003";
type Equipment = { id?: string; name: string; equipment_type?: string; status?: string };
type Process = { id: string; name: string; sequence_order?: number; status?: string; equipment?: Equipment[]; inputs?: Array<{ item_name?: string; flow_type?: string }>; outputs?: Array<{ item_name?: string; flow_type?: string }> };

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<Process[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Loading the saved process map…");

  const loadProcesses = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<Process[]>(`/api/assessments/${ASSESSMENT_ID}/processes`);
      setProcesses(result);
      setMessage(result.length ? `${result.length} process steps loaded from this assessment.` : "No process steps have been saved yet.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The process map could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadProcesses(); }, [loadProcesses]);

  return <main><Nav /><div className="topbar"><div><p className="eyebrow">03 / Process mapping</p><h1>Facility process map</h1><p>Verify the equipment and material flows attached to each operating step.</p></div><Link className="secondary-link" href="/template">← Template</Link></div>
    <section className="process-toolbar card"><div><p className="eyebrow">SAVED ASSESSMENT PROCESS FLOW</p><h2>{loading ? "Checking saved steps…" : `${processes.length} process ${processes.length === 1 ? "step" : "steps"}`}</h2><p>{message}</p></div><button onClick={loadProcesses} disabled={loading}>{loading ? "Refreshing…" : "Refresh process map"}</button></section>
    {!loading && processes.length === 0 && <section className="card empty"><div className="empty-icon">⌂</div><h2>No process map yet</h2><p>Load the industry starter map first, then return here to review the saved process steps.</p><Link className="primary-cta" href="/template">Load starter map <span>→</span></Link></section>}
    {processes.length > 0 && <section className="process-flow">{processes.map((process, index) => <article className="card process-card" key={process.id}><div className="process-number">{index + 1}</div><div className="process-body"><div className="process-heading"><div><span className="step-label">PROCESS STEP {String(index + 1).padStart(2, "0")}</span><h2>{process.name}</h2></div><div className="process-actions"><span className="pill">{process.status || "SUGGESTED"}</span><Link className="soft-button edit-link" href={`/equipment/${process.id}`}>Edit equipment</Link></div></div><div className="process-columns"><div><small>Equipment</small>{process.equipment?.length ? <div className="chip-list">{process.equipment.map(item => <span className="chip" key={item.id || item.name}>{item.name}</span>)}</div> : <p className="muted">No equipment recorded</p>}</div><div><small>Inputs and outputs</small><p className="flow-text">{[...(process.inputs || []), ...(process.outputs || [])].map(item => item.item_name).filter(Boolean).join(" · ") || "No flows recorded"}</p></div></div></div></article>)}</section>}
    <section className="card process-next"><div><p className="eyebrow">NEXT STEP</p><h2>Identify possible emission sources</h2><p>Use the saved processes, equipment and flows as inputs to the rule engine and ML suggestion layer.</p></div><Link className="primary-cta" href="/workflow">Find possible sources <span>→</span></Link></section>
  </main>;
}
