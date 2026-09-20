const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    const health = API_BASE ? `${API_BASE}/api/health` : '/api/health';
    throw new Error(
      API_BASE
        ? `Cannot reach the server. Open ${health}, wait until it shows ok, then try again (free server may take ~1 min to wake).`
        : 'API URL is missing. Set VITE_API_URL on Vercel and redeploy.',
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export type VariantRow = {
  variant_id: number;
  snapshot_id: number;
  colour?: string | null;
  size?: string | null;
  stock_qty?: number | null;
  mrp?: number | null;
  item_code?: string | null;
  purchase_qty?: number | null;
  purchase_rate?: number | null;
  purchase_amount?: number | null;
  difference?: number | null;
  stock_amount?: number | null;
  pdf_page?: number | null;
  original_product_text?: string | null;
  filename?: string | null;
  report_date?: string | null;
};

export type SearchGroup = {
  product_id: number;
  design_number?: string | null;
  design_name?: string | null;
  category?: string | null;
  supplier?: string | null;
  report_id?: number | null;
  report_date?: string | null;
  filename?: string | null;
  variants: VariantRow[];
  total_stock: number;
};

export type SearchResponse = {
  query: string;
  report_id?: number | null;
  colour_message?: string | null;
  count: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  results: SearchGroup[];
};

export type PreviewResponse = {
  report_id: number;
  filename: string;
  report_date?: string | null;
  category: string;
  supplier?: string | null;
  pages: number;
  rows_detected: number;
  rows_parsed: number;
  rows_review: number;
  extraction_method?: string;
  warnings: string[];
  sample_rows: Record<string, unknown>[];
  status: string;
  /** True when this filename replaced a previous upload of the same name. */
  replaced?: boolean;
};

export type Dashboard = {
  latest_report?: Record<string, unknown> | null;
  total_designs: number;
  total_stock_units: number;
  fashion_products: number;
  jewellery_products: number;
  suppliers: number;
  low_stock_products: number;
  out_of_stock_products: number;
  recent_uploads: Record<string, unknown>[];
  low_stock_threshold: number;
};

export type Report = {
  id: number;
  filename: string;
  report_date?: string | null;
  category: string;
  status: string;
  total_rows: number;
  rows_parsed: number;
  rows_review: number;
  uploaded_at: string;
  supplier_name?: string | null;
};

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  dashboard: () => request<Dashboard>('/api/dashboard'),
  reports: () => request<{ reports: Report[] }>('/api/reports'),
  filters: (reportId?: number | null) =>
    request<{
      colours: string[];
      sizes: string[];
      suppliers: string[];
      categories: string[];
      stock_statuses: { value: string; label: string }[];
    }>(`/api/search/filters${reportId ? `?report_id=${reportId}` : ''}`),
  search: (params: Record<string, string | number | boolean | undefined | null>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    return request<SearchResponse>(`/api/search?${qs.toString()}`);
  },
  uploadPdf: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<PreviewResponse>('/api/upload/pdf', { method: 'POST', body: form });
  },
  getPreview: (reportId: number) => request<PreviewResponse>(`/api/upload/preview/${reportId}`),
  confirmImport: (reportId: number, includeReviewRows = false) =>
    request<{ status: string; imported_rows: number; skipped_review_rows: number }>(
      `/api/upload/confirm/${reportId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_review_rows: includeReviewRows }),
      },
    ),
  design: (productId: number, reportId?: number | null) =>
    request<Record<string, unknown>>(
      `/api/designs/${productId}${reportId ? `?report_id=${reportId}` : ''}`,
    ),
  source: (snapshotId: number) => request<Record<string, unknown>>(`/api/source/${snapshotId}`),
  exportCsvUrl: (params: Record<string, string | number | boolean | undefined | null>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    return `/api/export/csv?${qs.toString()}`;
  },
  exportXlsxUrl: (params: Record<string, string | number | boolean | undefined | null>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
    return `/api/export/xlsx?${qs.toString()}`;
  },
};

export function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `₹${Number(value).toLocaleString('en-IN')}`;
}

export function formatQty(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-IN');
}
