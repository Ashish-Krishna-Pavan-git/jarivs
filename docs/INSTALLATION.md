# Installation Guide

JARVIS is usable with Docker without installing Python or Node locally. Docker Desktop is the recommended first setup.

## 1. Prepare configuration

From the repository root, create your local environment file.

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

For a first local run, leave the optional AI and notification keys blank. Before exposing JARVIS outside your machine, set unique values for `JWT_SECRET`, `FLASK_SECRET_KEY`, and `JARVIS_ENCRYPTION_KEY`.

## 2. Start JARVIS

```bash
docker compose up --build
```

Open `http://localhost:7860`. The health endpoint is `http://localhost:7860/health`.

## 3. First login

When `ADMIN_PASSWORD` is empty, the first account is:

- Username: `admin`
- Password: `admin123!ChangeMe`

JARVIS requires the current password and a new password of at least 12 characters before the dashboard becomes available. Set `ADMIN_PASSWORD` before the first start if you do not want the default first-run password.

## 4. First useful workflow

1. Sign in and change the temporary password.
2. In Admin -> Sources, confirm or add feeds.
3. In Admin -> Models, enable a configured provider. Use the environment-variable name for its API key, for example `GEMINI_API_KEY`.
4. Run a manual collection cycle from Admin -> Dashboard.
5. Open User -> Feed and Reports to inspect output.
6. Add Telegram or Slack in User -> Notifications when you want delivery.

## Local development

Python backend:

```bash
pip install -r requirements.txt
python app.py
```

Frontend development server:

```bash
cd frontend
npm install
npm run dev
```

The Vite server proxies API calls to Flask on port `7860`. Build the production bundle with `npm run build`.

## Existing installations

If a `jarvis-data/` folder is next to this repository, Docker mounts it read-only. It is detected automatically; JARVIS continues to write all new runtime data to the `jarvis_data` Docker volume. See [Migration](MIGRATION.md) before moving or backing up old data.
