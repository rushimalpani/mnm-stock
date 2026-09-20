import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  api,
  formatMoney,
  formatQty,
  type Report,
  type SearchGroup,
  type SearchResponse,
  type VariantRow,
} from '../api';
import { SourceModal } from '../components/SourceModal';

const PAGE_SIZE = 10;

export function SearchPage() {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [reportId, setReportId] = useState('latest');
  const [reports, setReports] = useState<Report[]>([]);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [colour, setColour] = useState('');
  const [stockStatus, setStockStatus] = useState('');
  const [page, setPage] = useState(1);
  const searchSeq = useRef(0);

  useEffect(() => {
    api.reports().then((r) => setReports(r.reports.filter((x) => x.status === 'imported')));
  }, []);

  const queryParams = useMemo(() => {
    const rid =
      reportId && reportId !== 'latest' && reportId !== 'all' ? Number(reportId) : undefined;
    return {
      q,
      latest: reportId === 'latest',
      report_id: rid,
      category: category || undefined,
      colour: colour || undefined,
      stock_status: stockStatus || undefined,
      page,
      page_size: PAGE_SIZE,
    };
  }, [q, category, reportId, colour, stockStatus, page]);

  async function runSearch(e?: React.FormEvent, nextPage = page) {
    e?.preventDefault();
    const seq = ++searchSeq.current;
    setLoading(true);
    setError(null);
    // Clear previous cards immediately so stale results cannot linger
    setData(null);
    try {
      const rid =
        reportId && reportId !== 'latest' && reportId !== 'all' ? Number(reportId) : undefined;
      const res = await api.search({
        q,
        latest: reportId === 'latest',
        report_id: rid,
        category: category || undefined,
        colour: colour || undefined,
        stock_status: stockStatus || undefined,
        page: nextPage,
        page_size: PAGE_SIZE,
      });
      if (seq !== searchSeq.current) return; // ignore outdated response
      setData(res);
      if (res.page && res.page !== nextPage) {
        setPage(res.page);
      }
    } catch (err) {
      if (seq !== searchSeq.current) return;
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      if (seq === searchSeq.current) setLoading(false);
    }
  }

  function searchFromStart(e?: React.FormEvent) {
    e?.preventDefault();
    setPage(1);
    void runSearch(undefined, 1);
  }

  useEffect(() => {
    void runSearch(undefined, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalPages = data?.total_pages ?? 1;
  const totalCount = data?.count ?? 0;
  const currentPage = data?.page ?? page;
  const from = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const to = Math.min(currentPage * PAGE_SIZE, totalCount);

  function goToPage(p: number) {
    const next = Math.min(Math.max(1, p), totalPages);
    setPage(next);
    void runSearch(undefined, next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <section className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm sm:rounded-3xl sm:p-6">
        <h1 className="font-[family-name:var(--font-display)] text-3xl leading-tight sm:text-4xl">
          Find your stock
        </h1>
        <p className="mt-2 text-base text-[var(--muted)] sm:text-lg">
          Search by <strong>design number</strong> or <strong>design name</strong> only.
          Example: <strong>131</strong> or <strong>Digital Print</strong>.
        </p>

        <form onSubmit={searchFromStart} className="mt-4 space-y-3 sm:mt-5 sm:space-y-4">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={
              category === 'jewellery'
                ? 'Jewellery code e.g. 1693 or 1657…'
                : 'Design number or design name…'
            }
            className="w-full rounded-2xl border-2 border-[var(--line)] bg-[var(--paper)] px-4 py-3.5 text-lg outline-none focus:border-[var(--accent)] sm:px-5 sm:py-4 sm:text-xl"
            enterKeyHint="search"
            autoCapitalize="off"
            autoCorrect="off"
          />
          <button
            type="submit"
            className="min-h-12 w-full rounded-2xl bg-[var(--accent)] px-5 py-3.5 text-lg font-semibold text-white active:bg-[var(--accent-2)] sm:w-auto sm:min-w-[220px] sm:text-xl"
          >
            {loading ? 'Searching…' : 'Search'}
          </button>

          <div className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {[
              { id: '', label: 'All' },
              { id: 'fashion', label: 'Fashion' },
              { id: 'jewellery', label: 'Jewellery' },
            ].map((c) => (
              <button
                key={c.id || 'all'}
                type="button"
                onClick={() => {
                  setCategory(c.id);
                  setPage(1);
                }}
                className={`shrink-0 rounded-full px-4 py-2.5 text-sm sm:text-base ${
                  category === c.id
                    ? 'bg-[var(--accent)] text-white'
                    : 'border border-[var(--line)] bg-[var(--paper)] text-[var(--muted)]'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>

          <label className="block text-base">
            <span className="mb-1 block font-medium">Which report?</span>
            <select
              className="min-h-12 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3"
              value={reportId}
              onChange={(e) => {
                setReportId(e.target.value);
                setPage(1);
              }}
            >
              <option value="all">All reports</option>
              <option value="latest">Only latest report</option>
              {reports.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.report_date || r.uploaded_at} — {r.filename}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="text-base text-[var(--accent)] underline"
            onClick={() => setShowMoreFilters((v) => !v)}
          >
            {showMoreFilters ? 'Hide extra filters' : 'More filters (optional)'}
          </button>

          {showMoreFilters && (
            <div className="grid gap-3 rounded-2xl bg-[var(--paper-2)] p-3 sm:grid-cols-2 sm:p-4">
              <label className="text-base">
                <span className="mb-1 block font-medium">Colour</span>
                <input
                  className="min-h-12 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3"
                  value={colour}
                  onChange={(e) => setColour(e.target.value)}
                  placeholder="e.g. Black"
                />
              </label>
              <label className="text-base">
                <span className="mb-1 block font-medium">Stock status</span>
                <select
                  className="min-h-12 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3"
                  value={stockStatus}
                  onChange={(e) => setStockStatus(e.target.value)}
                >
                  <option value="">Any</option>
                  <option value="in_stock">In stock</option>
                  <option value="low_stock">Low stock</option>
                  <option value="out_of_stock">Out of stock</option>
                </select>
              </label>
              <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => searchFromStart()}
                  className="min-h-12 rounded-xl bg-[var(--accent)] px-4 py-3 text-white"
                >
                  Apply
                </button>
                <a
                  className="min-h-12 rounded-xl border border-[var(--line)] bg-white px-4 py-3 text-center"
                  href={api.exportCsvUrl(queryParams)}
                >
                  Download CSV
                </a>
              </div>
            </div>
          )}
        </form>
      </section>

      {error && (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[var(--danger)]">{error}</p>
      )}
      {data?.colour_message && (
        <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[var(--warn)]">
          {data.colour_message}
        </p>
      )}

      <section className="space-y-3 sm:space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="font-[family-name:var(--font-display)] text-2xl sm:text-3xl">
            Results {data ? `(${totalCount})` : ''}
          </h2>
          {totalCount > 0 && (
            <p className="text-sm text-[var(--muted)] sm:text-base">
              Showing {from}–{to} of {totalCount}
            </p>
          )}
        </div>

        {!data?.results?.length && !loading && (
          <div className="rounded-2xl border border-dashed border-[var(--line)] bg-white/70 px-4 py-8 text-center sm:rounded-3xl sm:px-5 sm:py-10">
            <p className="text-lg font-medium sm:text-xl">
              {q.trim() || category || colour || stockStatus
                ? 'No matching stock'
                : 'Nothing found yet'}
            </p>
            <p className="mt-2 text-[var(--muted)]">
              {reports.length === 0 ? (
                <>
                  First go to <Link className="text-[var(--accent)] underline" to="/upload">Add PDF</Link> and
                  upload your stock report.
                </>
              ) : q.trim() ? (
                <>
                  No design matched <strong>{q.trim()}</strong>. For jewellery, search the style code (e.g.{' '}
                  <strong>1657</strong>), tap <strong>Jewellery</strong>, and pick that report.
                </>
              ) : (
                <>Try a design number, or choose Fashion / Jewellery above.</>
              )}
            </p>
          </div>
        )}

        {loading && (
          <p className="rounded-2xl border border-[var(--line)] bg-white/70 px-4 py-6 text-center text-[var(--muted)]">
            Searching…
          </p>
        )}

        {data?.results.map((group) => (
          <DesignCard
            key={`${group.category}-${group.design_number}-${group.variants[0]?.item_code ?? group.product_id}-${group.report_id ?? ''}`}
            group={group}
            onSource={setSourceId}
          />
        ))}

        {totalCount > PAGE_SIZE && (
          <nav
            className="flex flex-col items-stretch gap-3 rounded-2xl border border-[var(--line)] bg-white p-3 sm:flex-row sm:items-center sm:justify-between sm:rounded-3xl sm:px-4 sm:py-3"
            aria-label="Results pages"
          >
            <button
              type="button"
              disabled={loading || currentPage <= 1}
              onClick={() => goToPage(currentPage - 1)}
              className="min-h-12 rounded-xl border border-[var(--line)] bg-[var(--paper)] px-4 py-3 text-base font-semibold disabled:opacity-40"
            >
              ← Previous
            </button>
            <p className="text-center text-base font-medium">
              Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
            </p>
            <button
              type="button"
              disabled={loading || currentPage >= totalPages}
              onClick={() => goToPage(currentPage + 1)}
              className="min-h-12 rounded-xl bg-[var(--accent)] px-4 py-3 text-base font-semibold text-white disabled:opacity-40"
            >
              Next →
            </button>
          </nav>
        )}
      </section>

      {sourceId !== null && <SourceModal snapshotId={sourceId} onClose={() => setSourceId(null)} />}
    </div>
  );
}

function DesignCard({
  group,
  onSource,
}: {
  group: SearchGroup;
  onSource: (id: number) => void;
}) {
  const totalPurchase = group.variants.reduce((sum, v) => sum + Number(v.purchase_qty || 0), 0);

  return (
    <article className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm sm:rounded-3xl">
      <div className="border-b border-[var(--line)] bg-[var(--paper)] px-4 py-3 sm:px-5 sm:py-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)] sm:text-sm">
          Design number: {group.design_number || '—'}
        </p>
        <Link
          to={`/designs/${group.product_id}${group.report_id ? `?report_id=${group.report_id}` : ''}`}
          className="mt-1 block break-words font-[family-name:var(--font-display)] text-xl hover:text-[var(--accent)] sm:text-2xl"
        >
          {group.design_name}
        </Link>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:max-w-md">
          <div className="rounded-xl bg-white/80 px-3 py-2">
            <p className="text-xs text-[var(--muted)] sm:text-sm">Purchase stock</p>
            <p className="text-lg font-bold sm:text-xl">{formatQty(totalPurchase)} pcs</p>
          </div>
          <div className="rounded-xl bg-white/80 px-3 py-2">
            <p className="text-xs text-[var(--muted)] sm:text-sm">Available stock</p>
            <p className="text-lg font-bold text-[var(--accent)] sm:text-xl">
              {formatQty(group.total_stock)} pcs
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-2 p-3 md:hidden">
        {group.variants.map((v) => (
          <VariantMobileCard key={v.snapshot_id} v={v} onSource={onSource} />
        ))}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="min-w-full text-left text-base">
          <thead className="bg-white text-[var(--muted)]">
            <tr>
              <th className="px-5 py-3 font-semibold">Colour</th>
              <th className="px-5 py-3 font-semibold">Purchase stock</th>
              <th className="px-5 py-3 font-semibold">Available stock</th>
              <th className="px-5 py-3 font-semibold">MRP</th>
              <th className="px-5 py-3 font-semibold">Size</th>
              <th className="px-5 py-3 font-semibold">Item code</th>
              <th className="px-5 py-3 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {group.variants.map((v) => (
              <tr key={v.snapshot_id} className="border-t border-[var(--line)]">
                <td className="px-5 py-3 font-semibold">{v.colour || '—'}</td>
                <td className="px-5 py-3 text-lg font-semibold">{formatQty(v.purchase_qty)} pcs</td>
                <td className="px-5 py-3 text-xl font-bold text-[var(--accent)]">
                  {formatQty(v.stock_qty)} pcs
                </td>
                <td className="px-5 py-3 text-lg">{formatMoney(v.mrp)}</td>
                <td className="px-5 py-3">{v.size || '—'}</td>
                <td className="px-5 py-3 font-mono text-sm">{v.item_code || '—'}</td>
                <td className="px-5 py-3">
                  <button
                    type="button"
                    onClick={() => onSource(v.snapshot_id)}
                    className="text-[var(--accent)] underline"
                  >
                    Check PDF page
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function VariantMobileCard({
  v,
  onSource,
}: {
  v: VariantRow;
  onSource: (id: number) => void;
}) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--paper)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-[var(--muted)]">Colour</p>
          <p className="text-lg font-semibold">{v.colour || '—'}</p>
          {v.size ? <p className="text-sm text-[var(--muted)]">Size: {v.size}</p> : null}
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xs text-[var(--muted)]">Purchase</p>
          <p className="text-lg font-semibold">{formatQty(v.purchase_qty)} pcs</p>
          <p className="mt-1 text-xs text-[var(--muted)]">Available</p>
          <p className="text-2xl font-bold text-[var(--accent)]">{formatQty(v.stock_qty)} pcs</p>
          <p className="text-base font-medium">{formatMoney(v.mrp)}</p>
        </div>
      </div>
      <p className="mt-2 font-mono text-xs text-[var(--muted)]">{v.item_code || '—'}</p>
      <button
        type="button"
        onClick={() => onSource(v.snapshot_id)}
        className="mt-2 min-h-10 w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-[var(--accent)]"
      >
        Check PDF page
      </button>
    </div>
  );
}
