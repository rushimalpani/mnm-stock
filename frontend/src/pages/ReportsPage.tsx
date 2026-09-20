import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Report } from '../api';

export function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .reports()
      .then((r) => setReports(r.reports))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl sm:text-4xl">Old reports</h1>
      <p className="text-base text-[var(--muted)]">
        Every PDF you save is kept. You can search inside one date later.
      </p>
      {error && <p className="text-[var(--danger)]">{error}</p>}

      {!reports.length && (
        <p className="rounded-2xl border border-dashed border-[var(--line)] bg-white px-4 py-8 text-center text-[var(--muted)]">
          No reports yet. <Link className="text-[var(--accent)] underline" to="/upload">Add a PDF</Link>
        </p>
      )}

      {/* Mobile cards */}
      <div className="space-y-3 md:hidden">
        {reports.map((r) => (
          <article key={r.id} className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm">
            <p className="text-sm text-[var(--muted)]">{r.report_date || 'No date'}</p>
            <p className="break-all font-semibold">{r.filename}</p>
            <p className="mt-1 capitalize text-[var(--muted)]">
              {r.category} · {r.status}
              {r.supplier_name ? ` · ${r.supplier_name}` : ''}
            </p>
            <p className="mt-1 text-sm">
              Items: {r.rows_parsed}/{r.total_rows}
              {r.rows_review ? ` · ${r.rows_review} need check` : ''}
            </p>
            <div className="mt-3 flex gap-2">
              <a
                className="min-h-11 flex-1 rounded-xl border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-center text-[var(--accent)]"
                href={`/api/pdf/${r.id}`}
                target="_blank"
                rel="noreferrer"
              >
                Open PDF
              </a>
              {r.status === 'imported' && (
                <Link
                  className="min-h-11 flex-1 rounded-xl bg-[var(--accent)] px-3 py-2 text-center text-white"
                  to="/"
                >
                  Search
                </Link>
              )}
            </div>
          </article>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-2xl border border-[var(--line)] bg-white md:block">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-[var(--paper-2)] text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3">Report Date</th>
              <th className="px-4 py-3">Filename</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Supplier</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Rows</th>
              <th className="px-4 py-3">Open</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id} className="border-t border-[var(--line)]">
                <td className="px-4 py-3">{r.report_date || '—'}</td>
                <td className="px-4 py-3">{r.filename}</td>
                <td className="px-4 py-3 capitalize">{r.category}</td>
                <td className="px-4 py-3">{r.supplier_name || '—'}</td>
                <td className="px-4 py-3">{r.status}</td>
                <td className="px-4 py-3">
                  {r.rows_parsed}/{r.total_rows}
                  {r.rows_review ? ` · ${r.rows_review} review` : ''}
                </td>
                <td className="px-4 py-3">
                  <a className="text-[var(--accent)] hover:underline" href={`/api/pdf/${r.id}`} target="_blank" rel="noreferrer">
                    PDF
                  </a>
                  {r.status === 'imported' && (
                    <>
                      {' · '}
                      <Link className="text-[var(--accent)] hover:underline" to="/">
                        Search
                      </Link>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
