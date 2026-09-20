# PromptForward

PromptForward teaches users how to write better and more efficient AI prompts through guided practice and competition. The MVP focuses on image recreation: a user sees a target image and writes a prompt trying to recreate it, and PromptForward scores result quality, prompt quality, and efficiency.

Two modes:

- **Learning Mode**: the prompt is evaluated before image generation, with feedback on what to improve.
- **Game Mode**: two players compete to reproduce the same target image with one generation each.

## Running locally

```bash
# backend (needs MongoDB, plus OpenAI/Meta/Dropbox credentials)
cd backend
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env   # fill in the keys
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/python scripts/seed_challenges.py   # analyze target images in Dropbox

# frontend
cd frontend && npm install && npm run dev
```

Tests mock OpenAI, Meta, and Dropbox, and need only a local MongoDB on `mongodb://localhost:27017`:

```bash
cd backend && .venv/bin/pytest
```

## Documentation

- [MVP Spec](docs/MVP_SPEC.md) — architecture, scoring, data model, API routes, and MVP scope.

The spec is the source of truth. Any change to the plan is written into the spec before the code changes.
