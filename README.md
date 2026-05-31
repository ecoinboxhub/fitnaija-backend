# FitNaija Backend

## Backend setup

1. Create a Python virtual environment:
```bash
python -m venv venv
```

2. Activate the environment:
- macOS/Linux:
```bash
source venv/bin/activate
```
- Windows PowerShell:
```powershell
.\venv\Scripts\Activate.ps1
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy environment variables and update values for local development:
```bash
cp .env.example .env
```

5. Start the backend server locally:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

> For Render deployment, set these same environment variables in the Render dashboard and do not commit `.env` to source control.

## Backend environment

The backend reads the following environment variables from `.env`:

- `DATABASE_URL` — PostgreSQL connection URL. Example for Aiven:
  `postgresql://<username>:<password>@<host>:<port>/fitnaija_db?sslmode=require`
- `JWT_SECRET_KEY` — a strong secret for signing tokens.
- `ACCESS_TOKEN_EXPIRE_MINUTES` — token lifetime in minutes.
- `BACKEND_ALLOWED_ORIGINS` — comma-separated allowed frontend origins.

Recommended allowed origins for production:

```text
http://localhost:5173,https://<your-vercel-app>.vercel.app
```

## Render deployment

- Start command:
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

- Use Render environment variables to store sensitive data:
  - `DATABASE_URL`
  - `JWT_SECRET_KEY`
  - `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `BACKEND_ALLOWED_ORIGINS`

## Frontend setup

1. Change directory into the frontend folder:
```bash
cd ../fitnaija-frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file from the example and update the API base URL for your Render backend:
```bash
cp .env.example .env
```

4. Run the frontend in development mode:
```bash
npm run dev
```

5. Build the production bundle:
```bash
npm run build
```

## Vercel deployment

- Build command: `npm run build`
- Output directory: `dist`
- Environment variable to set in Vercel:

```text
VITE_API_BASE=https://<your-render-backend>.onrender.com
```

- Do not commit local `.env` files to Git. Use the Vercel dashboard for production values.
