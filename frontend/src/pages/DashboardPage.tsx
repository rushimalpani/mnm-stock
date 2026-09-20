import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, formatQty, type Dashboard } from '../api';

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'));
  }, []);

  if (error) return <p className="text-[var(--danger)]">{error}</p>;
  if (!data) return <p className="text-[var(--muted)]">Loading…</p>;

  const latest = data.latest_report;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl sm:text-4xl">Simple summary</h1>
        <p className="mt-2 text-base text-[var(--muted)] sm:text-lg">
          {latest
            ? `Latest report date: ${String(latest.report_date || '—')}`
            : 'No report saved yet. Add a PDF first.'}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-3">
        <Stat label="Total designs" value={String(data.total_designs)} />
        <Stat label="Pieces in stock" value={formatQty(data.total_stock_units)} />
        <Stat label="Fashion" value={String(data.fashion_products)} />
        <Stat label="Jewellery" value={String(data.jewellery_products)} />
        <Stat label="Low stock" value={String(data.low_stock_products)} tone="warn" />
        <Stat label="Out of stock" value={String(data.out_of_stock_products)} tone="danger" />
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
        <Link
          to="/"
          className="min-h-12 rounded-2xl bg-[var(--accent)] px-5 py-3 text-center font-semibold text-white"
        >
          Find stock
        </Link>
        <Link
          to="/upload"
          className="min-h-12 rounded-2xl border border-[var(--line)] bg-white px-5 py-3 text-center font-semibold"
        >
          Add PDF
        </Link>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'warn' | 'danger';
}) {
  const color =
    tone === 'warn' ? 'text-[var(--warn)]' : tone === 'danger' ? 'text-[var(--danger)]' : 'text-[var(--ink)]';
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-white p-3 shadow-sm sm:rounded-3xl sm:p-5">
      <p className="text-xs text-[var(--muted)] sm:text-base">{label}</p>
      <p className={`mt-1 font-[family-name:var(--font-display)] text-2xl sm:mt-2 sm:text-4xl ${color}`}>
        {value}
      </p>
    </div>
  );
}
