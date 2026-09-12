import Link from "next/link";

export default function Nav() {
  return <nav className="nav" aria-label="Layer 1 navigation">
    <Link className="brand" href="/">EmissionLens</Link>
    <div className="nav-links">
      <Link href="/workflow">Workflow</Link>
      <Link href="/">Activity data</Link>
      <Link href="/calculations">Calculations</Link>
    </div>
  </nav>;
}
