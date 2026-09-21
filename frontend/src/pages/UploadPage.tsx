import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, formatMoney, formatQty, stockQtyClass, type PreviewResponse } from '../api';

export function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [includeReview, setIncludeReview] = useState(false);
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    setConfirmMsg(null);
    try {
      setPreview(await api.uploadPdf(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }, []);

  async function confirmImport() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.confirmImport(preview.report_id, includeReview);
      setConfirmMsg(`Saved ${res.imported_rows} items. You can now search them.`);
      setPreview({ ...preview, status: 'imported' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <section className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm sm:rounded-3xl sm:p-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">Step 1</p>
        <h1 className="mt-1 font-[family-name:var(--font-display)] text-3xl sm:text-4xl">
          Add your stock PDF
        </h1>
        <p className="mt-2 text-base text-[var(--muted)] sm:text-lg">
          Choose the supplier stock report PDF from your phone or computer.
          Large fashion PDFs can take 1–3 minutes on the free server.
        </p>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) void handleFile(file);
          }}
          className={`mt-5 rounded-2xl border-4 border-dashed px-4 py-10 text-center sm:rounded-3xl sm:px-6 sm:py-16 ${
            dragging ? 'border-[var(--accent)] bg-teal-50' : 'border-[var(--line)] bg-[var(--paper)]'
          }`}
        >
          <p className="hidden font-[family-name:var(--font-display)] text-2xl sm:block">Drop PDF here</p>
          <p className="hidden text-[var(--muted)] sm:mt-2 sm:block">or</p>
          <label className="inline-block w-full max-w-sm cursor-pointer rounded-2xl bg-[var(--accent)] px-6 py-4 text-lg font-semibold text-white active:bg-[var(--accent-2)] sm:mt-4 sm:w-auto sm:px-8 sm:text-xl">
            {busy ? 'Working… please wait (can take a few minutes)' : 'Choose PDF file'}
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
          </label>
        </div>
      </section>

      {error && (
        <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[var(--danger)]">{error}</p>
      )}
      {confirmMsg && (
        <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-base text-[var(--ok)] sm:text-lg">
          {confirmMsg}{' '}
          <Link to="/" className="font-semibold underline">
            Go find stock →
          </Link>
        </p>
      )}

      {preview && (
        <section className="space-y-4 rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm sm:rounded-3xl sm:p-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">Step 2</p>
          <h2 className="font-[family-name:var(--font-display)] text-2xl sm:text-3xl">Check before saving</h2>
          <p className="text-base text-[var(--muted)] sm:text-lg">
            Make sure the numbers look correct. Then tap Save.
          </p>
          {preview.replaced && (
            <p className="rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-base text-[var(--accent)]">
              Updated existing report for this file name. Previous stock data and PDF for this file were
              replaced.
            </p>
          )}

          <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
            <Meta label="File name" value={preview.filename} />
            <Meta label="Report date" value={preview.report_date || 'Not found'} />
            <Meta
              label="Type"
              value={
                preview.category === 'fashion'
                  ? 'Fashion'
                  : preview.category === 'jewellery'
                    ? 'Jewellery'
                    : preview.category
              }
            />
            <Meta label="Supplier" value={preview.supplier || 'Not found'} />
            <Meta label="Pages" value={String(preview.pages)} />
            <Meta label="Items found" value={String(preview.rows_detected)} big />
            <Meta label="Ready" value={String(preview.rows_parsed)} big />
            <Meta label="Need check" value={String(preview.rows_review)} warn={preview.rows_review > 0} />
          </div>

          {preview.rows_detected === 0 && (
            <p className="rounded-2xl bg-amber-50 px-4 py-3 text-[var(--warn)]">
              No stock items found in this PDF. Try another file.
            </p>
          )}

          {preview.rows_review > 0 && (
            <p className="rounded-2xl bg-amber-50 px-4 py-3 text-[var(--warn)]">
              {preview.rows_review} items look unclear. They will be skipped unless you tick the box below.
            </p>
          )}

          {/* Mobile preview cards */}
          <div className="space-y-2 md:hidden">
            {preview.sample_rows.slice(0, 15).map((row, idx) => (
              <div key={idx} className="rounded-xl border border-[var(--line)] bg-[var(--paper)] p-3">
                <p className="text-sm text-[var(--muted)]">Design {String(row.design_number ?? '—')}</p>
                <p className="break-words font-semibold">
                  {String(row.design_name ?? row.original_product_text ?? '—')}
                </p>
                <div className="mt-2 flex items-end justify-between gap-2">
                  <div className="text-sm">
                    <p>
                      {String(row.colour ?? '—')} · {String(row.size ?? '—')}
                    </p>
                    <p className="font-mono text-xs text-[var(--muted)]">{String(row.item_code ?? '—')}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-[var(--muted)]">Purchase</p>
                    <p className="text-lg font-semibold">{formatQty(row.purchase_qty as number | null)}</p>
                    <p className="mt-1 text-xs text-[var(--muted)]">Available</p>
                    <p className={stockQtyClass(row.stock_qty as number | null, 'text-2xl font-bold')}>
                      {formatQty(row.stock_qty as number | null)}
                    </p>
                    <p className="text-sm">{formatMoney(row.mrp as number | null)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop table */}
          <div className="hidden overflow-x-auto rounded-2xl border border-[var(--line)] md:block">
            <table className="min-w-full text-left text-base">
              <thead className="bg-[var(--paper-2)] text-[var(--muted)]">
                <tr>
                  <th className="px-3 py-3">Design</th>
                  <th className="px-3 py-3">Name</th>
                  <th className="px-3 py-3">Colour</th>
                  <th className="px-3 py-3">Size</th>
                  <th className="px-3 py-3">Item code</th>
                  <th className="px-3 py-3">Purchase stock</th>
                  <th className="px-3 py-3">Available stock</th>
                  <th className="px-3 py-3">Price (MRP)</th>
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.slice(0, 20).map((row, idx) => (
                  <tr key={idx} className="border-t border-[var(--line)]">
                    <td className="px-3 py-3 font-semibold">{String(row.design_number ?? '—')}</td>
                    <td className="px-3 py-3">{String(row.design_name ?? row.original_product_text ?? '—')}</td>
                    <td className="px-3 py-3">{String(row.colour ?? '—')}</td>
                    <td className="px-3 py-3">{String(row.size ?? '—')}</td>
                    <td className="px-3 py-3 font-mono text-sm">{String(row.item_code ?? '—')}</td>
                    <td className="px-3 py-3 text-lg font-semibold">
                      {formatQty(row.purchase_qty as number | null)}
                    </td>
                    <td className={stockQtyClass(row.stock_qty as number | null, 'px-3 py-3 text-lg font-bold')}>
                      {formatQty(row.stock_qty as number | null)}
                    </td>
                    <td className="px-3 py-3">{formatMoney(row.mrp as number | null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <label className="flex min-h-12 items-center gap-3 text-base">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={includeReview}
              onChange={(e) => setIncludeReview(e.target.checked)}
            />
            Also save unclear items
          </label>

          <p className="text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">Step 3</p>
          <button
            type="button"
            disabled={busy || preview.status === 'imported' || preview.rows_detected === 0}
            onClick={() => void confirmImport()}
            className="min-h-14 w-full rounded-2xl bg-[var(--accent)] px-6 py-4 text-lg font-semibold text-white disabled:opacity-40 sm:w-auto sm:text-xl"
          >
            {preview.status === 'imported' ? 'Already saved' : 'Save stock to search'}
          </button>
        </section>
      )}
    </div>
  );
}

function Meta({
  label,
  value,
  warn,
  big,
}: {
  label: string;
  value: string;
  warn?: boolean;
  big?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-2.5 sm:rounded-2xl sm:px-4 sm:py-3 ${
        warn ? 'border-amber-300 bg-amber-50' : 'border-[var(--line)] bg-[var(--paper)]'
      }`}
    >
      <p className="text-xs text-[var(--muted)] sm:text-sm">{label}</p>
      <p
        className={`mt-1 break-all font-semibold capitalize ${
          big ? 'text-2xl text-[var(--accent)] sm:text-3xl' : 'text-base sm:text-lg'
        }`}
      >
        {value}
      </p>
    </div>
  );
}
