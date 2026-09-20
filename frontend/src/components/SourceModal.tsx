import { useEffect, useState } from 'react';
import { api } from '../api';

export function SourceModal({
  snapshotId,
  onClose,
}: {
  snapshotId: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .source(snapshotId)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'));
  }, [snapshotId]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close" onClick={onClose} />
      <div className="safe-bottom relative max-h-[92vh] w-full overflow-auto rounded-t-3xl bg-white p-5 shadow-xl sm:max-w-lg sm:rounded-3xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="font-[family-name:var(--font-display)] text-xl sm:text-2xl">PDF source</h3>
          <button
            type="button"
            onClick={onClose}
            className="min-h-10 min-w-10 rounded-full bg-[var(--paper-2)] px-3 text-[var(--muted)]"
          >
            ✕
          </button>
        </div>
        {error && <p className="text-[var(--danger)]">{error}</p>}
        {data && (
          <dl className="space-y-3 text-base">
            <div>
              <dt className="text-sm text-[var(--muted)]">PDF file</dt>
              <dd className="break-all font-medium">{String(data.filename ?? '—')}</dd>
            </div>
            <div>
              <dt className="text-sm text-[var(--muted)]">Page number</dt>
              <dd className="font-medium">{String(data.pdf_page ?? '—')}</dd>
            </div>
            <div>
              <dt className="text-sm text-[var(--muted)]">Report date</dt>
              <dd className="font-medium">{String(data.report_date ?? '—')}</dd>
            </div>
            <div>
              <dt className="text-sm text-[var(--muted)]">Item code</dt>
              <dd className="font-mono">{String(data.item_code ?? '—')}</dd>
            </div>
            <div>
              <dt className="text-sm text-[var(--muted)]">Original text from PDF</dt>
              <dd className="break-words rounded-xl bg-[var(--paper-2)] p-3">
                {String(data.original_product_text ?? '—')}
              </dd>
            </div>
            {(data as { report_id?: number }).report_id ? (
              <a
                className="inline-flex min-h-12 w-full items-center justify-center rounded-2xl bg-[var(--accent)] px-4 py-3 text-center font-semibold text-white sm:w-auto"
                href={`/api/pdf/${String((data as { report_id?: number }).report_id)}`}
                target="_blank"
                rel="noreferrer"
              >
                Open PDF
              </a>
            ) : null}
          </dl>
        )}
      </div>
    </div>
  );
}
