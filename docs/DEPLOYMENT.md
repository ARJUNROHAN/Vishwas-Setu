# GitHub Pages and Render

The React frontend runs on GitHub Pages. FastAPI, the database, uploaded files and the deadline scheduler run on Render. The frontend uses hash routes so refreshing any screen works on Pages.

## Deploy the backend

1. Push this project to `ARJUNROHAN/Vishwas-Setu` on the `main` branch.
2. Sign into Render and create a **Blueprint** from the repository. Render reads `render.yaml` and creates the **Free** `vishwas-setu-api` service. Review that the plan is Free before deploying.
3. Wait until the deploy completes, then open the service URL followed by `/api/health`. It should return `{"ok":true}`.
4. Copy the actual service URL. Render may add a suffix if the requested name is taken.

## Deploy the frontend

1. In GitHub, open **Settings → Secrets and variables → Actions → Variables**.
2. Add a repository variable named `VITE_API_BASE_URL`. Set it to the actual Render service URL plus `/api`, for example `https://your-service.onrender.com/api`. This URL is public configuration, not a secret.
3. Open **Settings → Pages**, and choose **GitHub Actions** as the source.
4. Open **Actions → Deploy GitHub Pages → Run workflow**. After it succeeds, open `https://arjunrohan.github.io/Vishwas-Setu/`.

The Pages build is skipped until the backend URL is configured. Set the variable and run the workflow once Render is ready.

## Demo behavior

- Use the demo accounts on the login page; their password is `demo123`.
- Officials and institutions use the same backend, so actions are shared across browsers and roles.
- On Render's Free plan, the server sleeps after 15 minutes without requests. The next visit can take about a minute to start it. Open the demo before presenting.
- SQLite and uploads live on Render's temporary filesystem. A redeploy, restart or sleep resets them, and startup creates fresh fictional demo data. This setup is for presenting the prototype, not keeping permanent records.
- Email notifications are simulated in the outbox; no real messages are sent.
- The generated JWT secret is stored by Render, not in the repository.

For persistent records, move the database to managed PostgreSQL and uploads to object storage, or use a paid instance with a persistent disk. No paid resources are included in this Blueprint.

## Check locally

```powershell
cd backend
python -m pytest -q
uvicorn app.main:app --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

For a Pages-style build:

```powershell
$env:VITE_BASE_PATH = '/Vishwas-Setu/'
$env:VITE_PAGES = 'true'
npm run build
npm run preview
```

Open `http://localhost:4173/Vishwas-Setu/`. With no external API URL set, preview proxies `/api` to the local backend.
