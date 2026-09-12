import Link from "next/link";

export default function Nav() {
  return <nav className="nav" aria-label="Layer 1 navigation">
    <Link className="brand" href="/" aria-label="EmissionLens home">
      <span className="brand-mark" aria-hidden="true" />
      <span className="brand-copy"><strong>EmissionLens</strong><small>Carbon intelligence</small></span>
    </Link>
    <div className="nav-links">
      <Link href="/">Overview</Link>
      <Link href="/processes">Process map</Link>
      <Link href="/workflow">Source review</Link>
      <Link href="/calculations">Emissions</Link>
    </div>
    <span className="nav-status">Layer 1 active</span>
  </nav>;
}
