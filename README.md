# Supplier Stock Search & Inventory Management

Completely free, local, self-hosted stock search for Fashion/Lehenga and Jewellery supplier PDFs.

## Stack (₹0)

- Frontend: React + Vite + TypeScript + Tailwind CSS
- Backend: Python + FastAPI
- Database: SQLite
- PDF: PyMuPDF (+ pdfplumber fallback)
- No OpenAI / paid OCR / paid cloud DB / subscriptions

## Quick start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API: http://127.0.0.1:8000  
Docs: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://127.0.0.1:5173

### Sample PDFs

Place your real supplier PDFs in `samples/` (optional) and upload them from the UI.

For automated tests only, fixture PDFs are generated in-memory/temp by the test suite.

### Tests

```bash
cd backend
./venv/bin/python -m pytest tests/ -v
```

## Features

1. Upload supplier stock PDF → extract → parse → preview → confirm import
2. Historical snapshots (never overwrite prior days)
3. Search by design number, name, colour, size, item code, supplier
4. Design detail + View Source (filename, page, original text)
5. Dashboard, filters, CSV/Excel export

## Important data rules

- Design number comes from the **product/design name** (e.g. `134-Digital Print` → `134`), never from page/entry numbers
- **Stock Qty** is remaining stock — not Purchase Qty
- Uncertain rows are marked for review and skipped unless you opt in

## Optional free static hosting (later)

See **[DEPLOY.md](./DEPLOY.md)** for step-by-step:

- Frontend → **Vercel**
- Backend → **Render**

Local use remains the default and cheapest option.
