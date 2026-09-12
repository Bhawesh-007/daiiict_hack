"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Nav from "@/app/components/Nav";
import { api } from "@/lib/api-client";

const ASSESSMENT_ID = "10000000-0000-4000-8000-000000000003";
type Equipment = { id?: string; name: string; equipment_type?: string; capacity?: string; fuel_type?: string; energy_type?: string; description?: string };
type Process = { id: string; name: string; equipment?: Equipment[] };

export default function EquipmentPage() {
  const params = useParams<{ processId: string }>();
  const processId = params.processId;
  const [process, setProcess] = useState<Process | null>(null);
  const [items, setItems] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("Loading equipment…");

  useEffect(() => { api<Process[]>(`/api/assessments/${ASSESSMENT_ID}/processes`).then(all => { const selected = all.find(item => item.id === processId); if (!selected) throw new Error("Process step not found."); setProcess(selected); setItems(selected.equipment || []); setMessage("Review or add equipment, then save the complete list."); }).catch(e => setMessage(e instanceof Error ? e.message : "Equipment could not be loaded.")).finally(() => setLoading(false)); }, [processId]);
  function update(index: number, field: keyof Equipment, value: string) { setItems(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item)); }
  function add() { setItems(current => [...current, { name: "", equipment_type: "", capacity: "", fuel_type: "", energy_type: "", description: "" }]); }
  function remove(index: number) { setItems(current => current.filter((_, itemIndex) => itemIndex !== index)); }
  async function save(event: FormEvent) { event.preventDefault(); if (items.some(item => !item.name.trim())) { setMessage("Every equipment item needs a name."); return; } setSaving(true); setMessage("Saving equipment…"); try { const result = await api<Equipment[]>(`/api/processes/${processId}/equipment`, { method: "PUT", body: JSON.stringify(items) }); setItems(result); setMessage(`${result.length} equipment item${result.length === 1 ? "" : "s"} saved successfully.`); } catch (e) { setMessage(e instanceof Error ? e.message : "Equipment could not be saved."); } finally { setSaving(false); } }

  return <main><Nav /><div className="topbar"><div><p className="eyebrow">PROCESS MAP · EQUIPMENT</p><h1>{process?.name || "Equipment details"}</h1><p>Add the equipment that actually exists in this process. Saving replaces the equipment list for this process step.</p></div><Link className="secondary-link" href="/processes">← Process map</Link></div><div className={message.includes("could not") || message.includes("needs") ? "notice" : "notice success"}>{message}</div>{loading ? <section className="card loading-card"><div className="spinner" /><p>Loading equipment…</p></section> : process && <form onSubmit={save}><section className="equipment-list">{items.map((item, index) => <article className="card equipment-card" key={item.id || index}><div className="equipment-top"><span className="equipment-number">{index + 1}</span><h2>Equipment {index + 1}</h2><button className="text-button" type="button" onClick={() => remove(index)}>Remove</button></div><div className="equipment-fields"><label>Name *<input value={item.name} onChange={e => update(index, "name", e.target.value)} placeholder="e.g. Diesel boiler" /></label><label>Type<input value={item.equipment_type || ""} onChange={e => update(index, "equipment_type", e.target.value)} placeholder="e.g. Boiler" /></label><label>Capacity<input value={item.capacity || ""} onChange={e => update(index, "capacity", e.target.value)} placeholder="e.g. 2 tonne/hour" /></label><label>Fuel type<input value={item.fuel_type || ""} onChange={e => update(index, "fuel_type", e.target.value)} placeholder="e.g. Diesel" /></label><label>Energy type<input value={item.energy_type || ""} onChange={e => update(index, "energy_type", e.target.value)} placeholder="e.g. Thermal" /></label><label className="wide">Description<textarea value={item.description || ""} onChange={e => update(index, "description", e.target.value)} placeholder="Optional context for source identification" /></label></div></article>)}</section><button className="add-equipment" type="button" onClick={add}>＋ Add equipment</button><section className="card form-actions"><Link className="secondary-link" href="/processes">Cancel</Link><button type="submit" disabled={saving}>{saving ? "Saving…" : "Save equipment"}</button></section></form>}</main>;
}
