# Local setup

How to run PromptForward on your own machine (Cursor, VS Code, or a plain
terminal). Takes about ten minutes the first time.

## What you need

- Git, Python 3.10+, Node 20.19.x or 22.12+, Docker (for MongoDB).
- The team's credentials for `backend/.env` (ask the project owner; they are
  never committed). One Meta key covers both the evaluators and image
  generation. Dropbox is a single shared account behind the backend — nobody
  logs in to Dropbox in the app, so no redirect URI or "development user" is
  needed on the Dropbox app page.

## 1. Clone

```bash
git clone https://github.com/some-kim/PromptForward.git
cd PromptForward
```

In Cursor: `Ctrl+Shift+P` → "Git: Clone" → paste the URL → Open.

## 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `backend/.env`. The values that are not secrets:

```
OPENAI_BASE_URL=https://api.meta.ai/v1
OPENAI_CHALLENGE_ANALYZER_MODEL=muse-spark-1.3
OPENAI_PROMPT_EVALUATOR_MODEL=muse-spark-1.3
OPENAI_RESULT_EVALUATOR_MODEL=muse-spark-1.3
META_API_BASE_URL=https://api.meta.ai/v1
META_IMAGE_MODEL=muse-image-1.0
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=promptforward
DROPBOX_CHALLENGES_FOLDER=/Challenges
DROPBOX_GENERATED_FOLDER=/Generated
```

The secrets you paste in from the owner: `OPENAI_API_KEY` and `META_API_KEY`
(both the Meta key while OpenAI is out of credits), `DROPBOX_APP_KEY`,
`DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`. Leave `DROPBOX_ACCESS_TOKEN`
empty — generated access tokens expire after ~4 hours; the refresh token does
not.

Start MongoDB and the API:

```bash
docker run -d --name pf-mongo -p 27017:27017 mongo:7
uvicorn app.main:app --reload --port 8000
```

`curl localhost:8000/api/health` should return `{"status":"ok",...}`.

## 3. Seed the problem set (once per database)

Problems, rubrics and progress live in MongoDB, so a fresh local database is
empty even though the target images are already in the shared Dropbox.

```bash
cd backend
python -m scripts.seed_curriculum
```

This uploads any missing target images to Dropbox, analyzes each of the 40
targets once with `muse-spark-1.3` (about 40 evaluator calls plus 40 reference
checks — a few dollars of the Meta budget), and warns if any reference prompt
scores below 70. Re-running is cheap: already-analyzed targets are skipped.
Add `--skip-check` to skip the reference scoring.

To avoid everyone re-seeding, the team can share one hosted MongoDB (Atlas free
tier): set the same `MONGODB_URI` in every `.env` and seed it once.

## 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The UI proxies `/api` to port 8000.

## 5. Checks

```bash
(cd backend  && PYTHONPATH=. pytest -q && ruff check .)
(cd frontend && npx tsc -b && npm run lint && npm run build)
```

## Troubleshooting

- **Images 404 / "expired_access_token"** — you are using a generated access
  token. Switch to `DROPBOX_REFRESH_TOKEN`.
- **Teammate sees an empty Problem Set** — their MongoDB was never seeded (step
  3) or points at a different `MONGODB_URI`. This is not a Dropbox permission
  issue.
- **Evaluate takes ~30 s** — normal on Meta's evaluator; identical prompts on
  the same problem are cached and return instantly after the first run.
- **Startup fails with a missing-variable error** — every `*_MODEL` variable
  must be set; the app refuses to start otherwise.
