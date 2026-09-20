# Deploy: Frontend → Vercel | Backend → Render
# =============================================

This app uses a React frontend and a FastAPI + SQLite backend.
Deploy them separately, then point the frontend at the backend URL.

Important (Render free tier):
- Without a Persistent Disk, SQLite + uploaded PDFs can be wiped when the service
  restarts or redeploys.
- Add a small Persistent Disk and set STOCK_DATA_DIR=/data (steps below).

--------------------------------
A. Push code to GitHub
--------------------------------

1. Create a GitHub repo and push this project (Mnm folder).
2. You will connect the same repo to both Vercel and Render.


--------------------------------
B. Backend on Render
--------------------------------

1. Go to https://render.com → Sign up / Log in.
2. New → Web Service → connect your GitHub repo.
3. Settings:

   | Field | Value |
   |-------|--------|
   | Name | mnm-stock-api (or any name) |
   | Root Directory | `backend` |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | Instance | Free |

4. Environment variables (Render → Environment):

   | Key | Value |
   |-----|--------|
   | `STOCK_DATA_DIR` | `/data` |
   | `CORS_ORIGINS` | `*`  (later change to your Vercel URL, e.g. `https://your-app.vercel.app`) |

5. Persistent Disk (recommended so stock data is not lost):

   - Render → your service → Disks → Add Disk
   - Name: `stock-data`
   - Mount path: `/data`
   - Size: 1 GB is enough to start

6. Click Deploy. Wait until it says Live.
7. Open: `https://YOUR-SERVICE.onrender.com/api/health`
   You should see: `{"status":"ok"}`

   Save this base URL, e.g. `https://mnm-stock-api.onrender.com`


--------------------------------
C. Frontend on Vercel
--------------------------------

1. Go to https://vercel.com → Sign up / Log in (GitHub is easiest).
2. Add New Project → import the same GitHub repo.
3. Settings:

   | Field | Value |
   |-------|--------|
   | Framework Preset | Vite |
   | Root Directory | `frontend` |
   | Build Command | `npm run build` |
   | Output Directory | `dist` |

4. Environment Variables:

   | Key | Value |
   |-----|--------|
   | `VITE_API_URL` | `https://YOUR-SERVICE.onrender.com`  (no trailing slash) |

5. Deploy.
6. Open your Vercel URL (e.g. `https://mnm-stock.vercel.app`).


--------------------------------
D. Connect CORS (after Vercel URL is known)
--------------------------------

1. In Render → Environment, set:

   `CORS_ORIGINS` = `https://your-app.vercel.app`

   (You can keep `*` if you prefer; locking it to Vercel is safer.)

2. Redeploy the Render service (or it may auto-restart).


--------------------------------
E. First use after deploy
--------------------------------

1. Open the Vercel site.
2. Go to Add PDF → upload your supplier stock PDF.
3. Confirm import.
4. Search by design number (e.g. `131`).

Note: Render free services sleep after ~15 minutes of no traffic.
The first request after sleep can take 30–60 seconds.


--------------------------------
F. Local development (unchanged)
--------------------------------

```bash
# Backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (uses Vite proxy; leave VITE_API_URL empty)
cd frontend
npm run dev
```


--------------------------------
G. Checklist if something fails
--------------------------------

- Frontend blank / network errors → check `VITE_API_URL` has no trailing slash
  and points to Render (`…onrender.com`), then Redeploy Vercel.
- CORS errors in browser console → set `CORS_ORIGINS` to your Vercel URL on Render.
- `/api/health` fails → Render service is sleeping or build failed; check Render logs.
- Data disappeared after redeploy → add Persistent Disk at `/data` and `STOCK_DATA_DIR=/data`.
- Upload timeout on large PDFs → Render free tier is slow; wait or upgrade later.


--------------------------------
I. Keep Render awake (every 5 minutes)
--------------------------------

Render free services sleep after ~15 minutes idle. To keep the API up
automatically (no laptop needed):

1. GitHub → your repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
   - Name: `RENDER_URL`
   - Value: `https://YOUR-SERVICE.onrender.com`  (no `/api`, no trailing slash)
3. Push the repo (workflow file is already at `.github/workflows/keep-render-awake.yml`)
4. **Actions** → **Keep Render Awake** → **Run workflow** once to test

GitHub will then ping `/api/health` about every 5 minutes.

Optional local loop (only if your laptop stays on):

```bash
python3 scripts/keep_render_awake.py --url https://YOUR-SERVICE.onrender.com
```
