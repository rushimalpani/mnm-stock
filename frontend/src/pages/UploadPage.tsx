import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, formatMoney, formatQty, stockQtyClass, type PreviewResponse } from '../api';

type BusyPhase = 'upload' | 'save' | null;

export function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [busyPhase, setBusyPhase] = useState<BusyPhase>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [includeReview, setIncludeReview] = useState(false);
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);

  const busy = busyPhase !== null;

  const handleFile = useCallback(async (file: File) => {
    setBusyPhase('upload');
    setError(null);
    setConfirmMsg(null);
    try {
      setPreview(await api.uploadPdf(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setPreview(null);
    } finally {
      setBusyPhase(null);
    }
  }, []);

  async function confirmImport() {
    if (!preview) return;
    setBusyPhase('save');
    setError(null);
    try {
      let res = await api.confirmImport(preview.report_id, includeReview);
      // Large reports save in the background — poll until done (avoids Render 502)
      if (res.status === 'importing') {
        const started = Date.now();
        while (Date.now() - started < 10 * 60 * 1000) {
          await new Promise((r) => setTimeout(r, 2000));
          const st = await api.confirmStatus(preview.report_id);
          if (st.status === 'imported') {
            res = st;
            break;
          }
          if (st.status === 'failed') {
            throw new Error(st.message || 'Save failed on server');
          }
          if (st.status !== 'importing') {
            // preview again / unexpected — keep waiting a bit
            if (st.status === 'preview') continue;
            res = st;
            break;
          }
        }
        if (res.status === 'importing') {
          throw new Error('Save is still running. Wait a minute, then search — or tap Save again.');
        }
      }
      setConfirmMsg(`Saved ${res.imported_rows} items. You can now search them.`);
      setPreview({ ...preview, status: 'imported' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusyPhase(null);
    }
  }

  const loaderTitle =
    busyPhase === 'save' ? 'Saving stock…' : busyPhase === 'upload' ? 'Reading PDF…' : '';
  const loaderHint =
    busyPhase === 'save'
      ? 'Writing items to the database. Large reports can take 1–3 minutes — keep this tab open.'
      : busyPhase === 'upload'
        ? 'Uploading and parsing the PDF. Large fashion reports can take 1–3 minutes — keep this tab open.'
        : '';

  return (
    <div className="space-y-4 sm:space-y-6">
      {busy && (
        <div
          className="sticky top-16 z-30 flex items-start gap-3 rounded-2xl border border-[var(--accent)]/30 bg-teal-50 px-4 py-3 shadow-sm sm:top-20 sm:items-center sm:px-5 sm:py-4"
          role="status"
          aria-live="polite"
          aria-busy="true"
        >
          <Spinner className="mt-0.5 h-7 w-7 shrink-0 text-[var(--accent)] sm:mt-0 sm:h-8 sm:w-8" />
          <div className="min-w-0">
            <p className="text-base font-semibold text-[var(--accent-2)] sm:text-lg">{loaderTitle}</p>
            <p className="mt-0.5 text-sm text-[var(--muted)] sm:text-base">{loaderHint}</p>
          </div>
        </div>
      )}

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
            if (busy) return;
            const file = e.dataTransfer.files?.[0];
            if (file) void handleFile(file);
          }}
          className={`mt-5 rounded-2xl border-4 border-dashed px-4 py-10 text-center sm:rounded-3xl sm:px-6 sm:py-16 ${
            dragging ? 'border-[var(--accent)] bg-teal-50' : 'border-[var(--line)] bg-[var(--paper)]'
          } ${busy ? 'opacity-60' : ''}`}
        >
          {busyPhase === 'upload' ? (
            <div className="flex flex-col items-center gap-3">
              <Spinner className="h-10 w-10 text-[var(--accent)]" />
              <p className="font-[family-name:var(--font-display)] text-xl sm:text-2xl">Reading PDF…</p>
              <p className="max-w-md text-[var(--muted)]">Please wait — do not close this page.</p>
            </div>
          ) : (
            <>
              <p className="hidden font-[family-name:var(--font-display)] text-2xl sm:block">Drop PDF here</p>
              <p className="hidden text-[var(--muted)] sm:mt-2 sm:block">or</p>
              <label className="inline-block w-full max-w-sm cursor-pointer rounded-2xl bg-[var(--accent)] px-6 py-4 text-lg font-semibold text-white active:bg-[var(--accent-2)] sm:mt-4 sm:w-auto sm:px-8 sm:text-xl">
                Choose PDF file
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
            </>
          )}
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
        <section
          className={`space-y-4 rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm sm:rounded-3xl sm:p-6 ${
            busyPhase === 'save' ? 'relative' : ''
          }`}
        >
          {busyPhase === 'save' && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-white/70 backdrop-blur-[1px] sm:rounded-3xl">
              <div className="mx-4 flex max-w-sm flex-col items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-6 py-5 text-center shadow-sm">
                <Spinner className="h-9 w-9 text-[var(--accent)]" />
                <p className="text-lg font-semibold">Saving stock…</p>
                <p className="text-sm text-[var(--muted)]">This can take a few minutes. Please wait.</p>
              </div>
            </div>
          )}

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
              disabled={busy}
              onChange={(e) => setIncludeReview(e.target.checked)}
            />
            Also save unclear items
          </label>

          <p className="text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">Step 3</p>
          <button
            type="button"
            disabled={busy || preview.status === 'imported' || preview.rows_detected === 0}
            onClick={() => void confirmImport()}
            className="inline-flex min-h-14 w-full items-center justify-center gap-3 rounded-2xl bg-[var(--accent)] px-6 py-4 text-lg font-semibold text-white disabled:opacity-40 sm:w-auto sm:text-xl"
          >
            {busyPhase === 'save' ? (
              <>
                <Spinner className="h-5 w-5 text-white" />
                Saving… please wait
              </>
            ) : preview.status === 'imported' ? (
              'Already saved'
            ) : (
              'Save stock to search'
            )}
          </button>
        </section>
      )}
    </div>
  );
}

function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
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
