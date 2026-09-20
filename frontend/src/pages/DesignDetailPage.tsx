import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, formatMoney, formatQty, stockQtyClass } from '../api';
import { SourceModal } from '../components/SourceModal';

export function DesignDetailPage() {
  const { productId } = useParams();
  const [params] = useSearchParams();
  const reportId = params.get('report_id');
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | null>(null);

  useEffect(() => {
    if (!productId) return;
    api
      .design(Number(productId), reportId ? Number(reportId) : null)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'));
  }, [productId, reportId]);

  if (error) return <p className="text-[var(--danger)]">{error}</p>;
  if (!data) return <p className="text-[var(--muted)]">Loading…</p>;

  const variants = (data.variants as Record<string, unknown>[]) || [];

  return (
    <div className="space-y-4 sm:space-y-5">
      <Link to="/" className="inline-flex min-h-10 items-center text-base text-[var(--accent)]">
        ← Back to search
      </Link>
      <header className="rounded-2xl border border-[var(--line)] bg-white p-4 sm:rounded-3xl sm:p-5">
        <p className="text-xs uppercase tracking-[0.14em] text-[var(--muted)] sm:text-sm">
          Design {String(data.design_number ?? '—')}
        </p>
        <h1 className="break-words font-[family-name:var(--font-display)] text-2xl sm:text-3xl">
          {String(data.design_name)}
        </h1>
        <p className="mt-2 text-base text-[var(--muted)]">
          {[data.category, data.supplier, data.report_date].filter(Boolean).join(' · ')}
        </p>
        <p className="mt-3 grid grid-cols-2 gap-2 sm:max-w-md">
          <span className="rounded-xl bg-[var(--paper)] px-3 py-2">
            <span className="block text-xs text-[var(--muted)]">Purchase stock</span>
            <strong className="text-xl">
              {formatQty(
                ((data.variants as Record<string, unknown>[]) || []).reduce(
                  (s, v) => s + Number(v.purchase_qty || 0),
                  0,
                ),
              )}
            </strong>
          </span>
          <span className="rounded-xl bg-[var(--paper)] px-3 py-2">
            <span className="block text-xs text-[var(--muted)]">Available stock</span>
            <strong className={stockQtyClass(data.total_stock as number, 'text-xl')}>
              {formatQty(data.total_stock as number)}
            </strong>
          </span>
        </p>
      </header>

      {/* Mobile cards */}
      <div className="space-y-3 md:hidden">
        {variants.map((v) => (
          <div
            key={String(v.id ?? v.snapshot_id)}
            className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm text-[var(--muted)]">Colour / Size</p>
                <p className="font-semibold">
                  {String(v.colour ?? '—')} · {String(v.size ?? '—')}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[var(--muted)]">Purchase</p>
                <p className="text-lg font-semibold">{formatQty(v.purchase_qty as number)}</p>
                <p className="mt-1 text-xs text-[var(--muted)]">Available</p>
                <p className={stockQtyClass(v.stock_qty as number, 'text-3xl font-bold')}>
                  {formatQty(v.stock_qty as number)}
                </p>
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-[var(--muted)]">Price (MRP)</dt>
                <dd className="font-medium">{formatMoney(v.mrp as number)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Item code</dt>
                <dd className="font-mono text-xs">{String(v.item_code ?? '—')}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Purchase rate</dt>
                <dd>{formatMoney(v.purchase_rate as number)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Difference</dt>
                <dd>{formatQty(v.difference as number)}</dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Stock amount</dt>
                <dd>{formatMoney(v.stock_amount as number)}</dd>
              </div>
            </dl>
            <button
              type="button"
              className="mt-3 min-h-11 w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] text-[var(--accent)]"
              onClick={() => setSourceId(Number(v.id))}
            >
              Check PDF page
            </button>
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-2xl border border-[var(--line)] bg-white md:block">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-[var(--paper-2)] text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2">Colour</th>
              <th className="px-3 py-2">Size</th>
              <th className="px-3 py-2">Purchase stock</th>
              <th className="px-3 py-2">Available stock</th>
              <th className="px-3 py-2">MRP</th>
              <th className="px-3 py-2">Item Code</th>
              <th className="px-3 py-2">Purchase Rate</th>
              <th className="px-3 py-2">Purchase Amount</th>
              <th className="px-3 py-2">Difference</th>
              <th className="px-3 py-2">Stock Amount</th>
              <th className="px-3 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {variants.map((v) => (
              <tr key={String(v.id ?? v.snapshot_id)} className="border-t border-[var(--line)]">
                <td className="px-3 py-2">{String(v.colour ?? '—')}</td>
                <td className="px-3 py-2">{String(v.size ?? '—')}</td>
                <td className="px-3 py-2 font-semibold">{formatQty(v.purchase_qty as number)}</td>
                <td className={stockQtyClass(v.stock_qty as number, 'px-3 py-2 font-bold')}>
                  {formatQty(v.stock_qty as number)}
                </td>
                <td className="px-3 py-2">{formatMoney(v.mrp as number)}</td>
                <td className="px-3 py-2 font-mono text-xs">{String(v.item_code ?? '—')}</td>
                <td className="px-3 py-2">{formatMoney(v.purchase_rate as number)}</td>
                <td className="px-3 py-2">{formatMoney(v.purchase_amount as number)}</td>
                <td className="px-3 py-2">{formatQty(v.difference as number)}</td>
                <td className="px-3 py-2">{formatMoney(v.stock_amount as number)}</td>
                <td className="px-3 py-2">
                  <button type="button" className="text-[var(--accent)]" onClick={() => setSourceId(Number(v.id))}>
                    View Source
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {sourceId !== null && <SourceModal snapshotId={sourceId} onClose={() => setSourceId(null)} />}
    </div>
  );
}
