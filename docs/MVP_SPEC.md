# PromptForward: Hackathon MVP

## Goal

PromptForward teaches users how to write **better and more efficient AI prompts** through guided practice and competition.

The initial MVP focuses on **image recreation**:

> A user sees a target image and writes a prompt trying to recreate it.

PromptForward evaluates:

1. **Result Quality**: How closely did the generated image match the target?
2. **Prompt Quality**: How effectively did the user describe what mattered?
3. **Efficiency**: How many resources and attempts were needed? (both modes)

There are two modes:

- **Learning Mode**: evaluates the prompt before image generation and teaches the user what to improve.
- **Game Mode**: two users compete to reproduce the same target image in a single generation each, balancing result quality and efficiency.

The architecture should remain generic enough to add **text-generation challenges** later.

---

## Stack Decision

```text
Backend:  Python 3.10+ + FastAPI (Motor async MongoDB driver, Pydantic models, tiktoken)
Frontend: React + Vite + TypeScript
```

Rationale: `tiktoken` (the fixed tokenizer this document requires) is native to Python, Pydantic models pair directly with OpenAI structured outputs for the three evaluators, and Motor supports the atomic conditional updates the generation limits need.

All code snippets in this document are illustrative pseudocode. Implement them in the chosen backend language. Do not mix languages in the backend.

Repository layout:

```text
backend/    FastAPI application, scoring services, seed script, tests
frontend/   React + Vite + TypeScript client
docs/       This specification
```

---

## Terminology

Use these terms consistently throughout the codebase.

### Challenge Analyzer

Analyzes a new target image and generates a structured rubric describing what matters in that image.

### Challenge Rubric

The structured criteria used to evaluate both:

- the user's prompt
- the generated image

### Stored Challenge Analysis

The rubric and metadata generated for a target image and persisted in MongoDB.

Do **not** call this a cache in the UI or architecture documentation.

MongoDB is the persistent source of truth for challenge analysis.

### Prompt Evaluator

Evaluates how well the user's prompt:

- covers the challenge rubric
- follows strong image-prompting practices

### Result Evaluator

Compares the generated image with the target image using the challenge rubric.

### Efficiency Score

A deterministic backend score based on resources used.

---

## Environment Variables

Create a `.env` file in the backend.

```env
# ============================================
# OpenAI
# ============================================

OPENAI_API_KEY=
# Optional: any OpenAI-compatible endpoint. Empty means OpenAI itself.
OPENAI_BASE_URL=

# Model names are read only from env.
# The app must fail fast at startup if any are empty.

OPENAI_CHALLENGE_ANALYZER_MODEL=
OPENAI_PROMPT_EVALUATOR_MODEL=
OPENAI_RESULT_EVALUATOR_MODEL=

# ============================================
# Meta (Meta Model API, Muse Image)
# ============================================

META_API_KEY=
META_API_BASE_URL=
META_IMAGE_MODEL=
META_IMAGE_TIMEOUT_MS=120000

# ============================================
# MongoDB
# ============================================

MONGODB_URI=
MONGODB_DB_NAME=promptforward

# ============================================
# Dropbox
# ============================================

# Dropbox access tokens expire after ~4 hours.
# Use a refresh token so the demo does not break.

DROPBOX_APP_KEY=
DROPBOX_APP_SECRET=
# One of the two: a refresh token (preferred) or a short-lived access token for a demo.
DROPBOX_REFRESH_TOKEN=
DROPBOX_ACCESS_TOKEN=
DROPBOX_CHALLENGES_FOLDER=/PromptForward/Challenges
DROPBOX_GENERATED_FOLDER=/PromptForward/Generated

# ============================================
# Application
# ============================================

APP_ENV=development
PORT=8000
CORS_ALLOW_ORIGINS=http://localhost:5173    # comma-separated; no wildcard
```

Create a `.env.example` with the same variables and empty values (keep non-secret defaults).

**Never commit actual API keys to Git.**

Add:

```gitignore
.env
.env.local
```

Validate all required env vars at startup and exit with a clear error listing any that are missing.

---

## Technology Stack

| Responsibility | Technology |
|---|---|
| Challenge Analyzer | OpenAI multimodal model |
| Prompt Evaluator | OpenAI model |
| Image Generator | Meta Muse Image (Meta Model API) |
| Result Evaluator | OpenAI multimodal model |
| Efficiency Score | Backend code |
| Token Counting | Backend code (fixed tokenizer, see below) |
| Target + Generated Image Storage | Dropbox |
| Persistent Data | MongoDB |

Model IDs are read from environment variables in one config module.

Do not scatter model names throughout the code.

---

## LLM Call Rules (apply to all three OpenAI services)

- Use **structured outputs** (JSON schema enforced by the API), not free-text JSON parsing.
- Use the lowest temperature the model supports, for scoring consistency.
- Send images to OpenAI as base64 data URLs read from Dropbox by the backend. Do not pass Dropbox paths.
- Validate every response in backend code (see each service). On invalid output, retry **once**. If it fails again, return an error to the client. A failed evaluation never consumes a generation.
- The LLM never computes final or weighted scores. It returns per-criterion judgments; backend code does all math.
- The evaluators talk to an OpenAI-compatible endpoint: `OPENAI_BASE_URL` (empty = OpenAI) plus the three model names. Any vision model with JSON-schema structured output can stand in — the demo currently runs them on Meta `muse-spark-1.3` while the OpenAI account is out of credits, and reverts by clearing `OPENAI_BASE_URL` and restoring the `gpt-4o` model names.

---

## High-Level Architecture

```text
                  DROPBOX
             Target Image Storage
                    │
                    ▼
                MongoDB
            Challenge Exists?
              ↙          ↘
            Yes           No
             │             │
             │      Challenge Analyzer
             │             │
             │       Generate Rubric
             │             │
             └──────┬──────┘
                    ▼
          Stored Challenge Analysis
                    │
                    ▼
                USER PROMPT
                    │
                    ▼
             Prompt Evaluator
                    │
           ┌────────┴────────┐
           ▼                 ▼
    Target Coverage     Craftsmanship
           │                 │
           └────────┬────────┘
                    ▼
              Prompt Score
                    │
                    ▼
              Image Generator
                    │
                    ▼
              Generated Image
                    │
                    ▼
              Result Evaluator
                    │
                    ▼
               Result Score
                    │
                    ▼
         Tokens + Generations
                    │
                    ▼
              Efficiency Score
                    │
                    ▼
                Final Score
```

---

## Challenge Creation

Challenge analysis is **fully automatic**. A developer only needs to add a target image.

Two entry points, both calling the same `createChallenge(image)` function:

1. **Seed script** (primary for the hackathon): reads every image in `DROPBOX_CHALLENGES_FOLDER` and calls `createChallenge` on each. Safe to re-run.
2. `POST /api/challenges` (dev only, disabled when `APP_ENV=production`): multipart image upload, capped at 10 MB.

### Flow

```text
Target Image
     ↓
Calculate SHA-256 Hash
     ↓
Search MongoDB
     ↓
Existing Challenge with current analysis version?
   ↙              ↘
 Yes              No
  ↓                ↓
Reuse        Challenge Analyzer
Stored             ↓
Analysis      Validate Rubric
                   ↓
            Store image in Dropbox (if not already there)
                   ↓
              Save MongoDB
```

---

## Identifying Known Images

Each image is identified by the SHA-256 hash of its bytes.

```text
imageHash = SHA256(image bytes)
```

Note: this only detects byte-identical files. A re-encoded or resized copy is treated as a new image. Acceptable for the MVP.

---

## Challenge Analyzer

The Challenge Analyzer receives:

```text
Target Image
```

and returns a weighted description of the visually important elements.

It should identify relevant features such as:

- Subject
- Action or state
- Environment
- Composition
- Spatial relationships
- Color
- Lighting
- Style / medium
- Mood

Not every image needs every category. The analyzer only includes characteristics that meaningfully affect recreation of the target.

### Output Schema (LLM)

```json
{
  "criteria": [
    {
      "category": "subject",
      "description": "yellow umbrella",
      "weight": 20,
      "critical": true
    }
  ]
}
```

`category` must be one of: `subject`, `action`, `environment`, `composition`, `spatial`, `color`, `lighting`, `style`, `mood`.

### Backend Validation

- 4 to 8 criteria.
- At least 1 and at most 4 criteria are `critical`.
- Every weight is a positive integer.
- **Weights are normalized by the backend to sum to exactly 100** (scale proportionally, round, then add any remainder to the largest weight). Do not rely on the LLM to sum correctly.
- The backend assigns ids `criterion_1 ... criterion_n`. The LLM does not produce ids.

---

## Example Challenge Rubric (after backend validation)

```json
{
  "criteria": [
    { "id": "criterion_1", "category": "subject",     "description": "yellow umbrella",                  "weight": 20, "critical": true  },
    { "id": "criterion_2", "category": "composition", "description": "umbrella positioned near the center", "weight": 15, "critical": true  },
    { "id": "criterion_3", "category": "environment", "description": "rainy city street at night",       "weight": 20, "critical": true  },
    { "id": "criterion_4", "category": "color",       "description": "blue reflections on wet pavement", "weight": 15, "critical": false },
    { "id": "criterion_5", "category": "subject",     "description": "multiple surrounding pedestrians", "weight": 15, "critical": false },
    { "id": "criterion_6", "category": "style",       "description": "realistic photography",            "weight": 15, "critical": false }
  ]
}
```

Criterion weights total `100`.

---

## Good Image Prompt Principles

PromptForward teaches users to provide the visual information that actually matters.

Strong image prompts generally communicate relevant information about:

- **Subject**: What is in the image?
- **Action / State**: What is happening?
- **Environment**: Where is it happening?
- **Composition**: Where are important elements positioned?
- **Spatial Relationships**: How do objects relate to one another?
- **Color**: Which colors materially define the target?
- **Lighting**: What type of lighting is present?
- **Style / Medium**: Photograph, illustration, watercolor, 3D render, etc.
- **Mood**: Only when atmosphere is visually important.

PromptForward does **not reward verbosity**.

This:

```text
A realistic nighttime photograph of a yellow umbrella centered
on a rainy city street, surrounded by pedestrians, with blue
city lights reflecting on the wet pavement.
```

is better than:

```text
Amazing beautiful highly detailed incredible professional
high quality yellow umbrella rainy city masterpiece ultra
detailed super realistic people cinematic beautiful.
```

The evaluator rewards **useful visual information**, not filler.

---

## Prompt Evaluator

The Prompt Evaluator receives:

```text
Challenge Rubric
+
User Prompt
```

It does **not** receive the target image. It evaluates:

1. **Target Coverage**
2. **Prompt Craftsmanship**

### Target Coverage

For every rubric criterion, the LLM returns one status:

```text
covered | partial | missing
```

Numeric conversion (backend):

```text
covered = 1.0
partial = 0.5
missing = 0.0
```

```python
target_coverage = sum(c.weight * STATUS_VALUE[c.status] for c in criteria)
```

Validation: the response must contain exactly one entry for every rubric id and no others.

### Prompt Craftsmanship

The LLM scores four properties, each an integer 0 to 100:

- **Clarity**: Is the prompt easy for an image model to understand?
- **Relevant Specificity**: Does it include useful details rather than vague descriptions?
- **Spatial Clarity**: Does it clearly communicate positions and relationships when relevant?
- **Conciseness**: Does it avoid repetition, filler, and contradictory instructions?

```python
craftsmanship = (
    clarity * 0.30
    + relevant_specificity * 0.30
    + spatial_clarity * 0.25
    + conciseness * 0.15
)
```

### Prompt Quality Score

```python
prompt_quality = target_coverage * 0.70 + craftsmanship * 0.30
```

### Full LLM Response Schema

```json
{
  "criteria": [
    { "id": "criterion_1", "status": "covered" },
    { "id": "criterion_2", "status": "missing" }
  ],
  "craftsmanship": {
    "clarity": 92,
    "relevantSpecificity": 78,
    "spatialClarity": 55,
    "conciseness": 91
  },
  "feedback": "You described the main subject and environment clearly, but you did not specify where the umbrella should appear in the composition."
}
```

Feedback rules:

- 1 to 3 sentences.
- The evaluator must **not rewrite the prompt** or supply replacement wording. The user makes the improvement.
- The "Missing / Needs improvement" list in the UI is built by the **backend** from criteria with status `missing` or `partial`, phrased by category (e.g. "Describe the composition", "Mention the lighting"). Do not show raw rubric descriptions to the user, since that hands them the answer.

---

## Learning Mode

### Flow

```text
Target Image
     ↓
User Writes Prompt
     ↓
Prompt Evaluator
     ↓
Pass?
 ┌───────────┐
 │           │
 No         Yes
 │           │
Feedback   Generate Image
 │           │
Revise        ↓
 │       Evaluate Result
 └──────→     ↓
           Results
```

Passing rule:

```python
passes = (
    prompt_quality >= 70
    and all(status != "missing" for c in criteria if c.critical)
)
```

### Server-Side Gate (required)

The gate must be enforced by the backend, not only the UI:

- Every evaluation is stored on the attempt (`promptEvaluations`).
- `generate` only succeeds if the **most recent** evaluation passed **and** its prompt text is identical to the prompt being generated. Otherwise return `409`.
- Learning Mode allows up to 3 generations per attempt. Each one needs its own passing evaluation. Enforce the limit atomically.
- An evaluation is **consumed** by the generation it unlocks: the atomic reservation records the evaluation's id and refuses any later reservation that would reuse it, so one passing evaluation can never unlock two generations (including concurrent requests).
- Generation numbers come from a monotonic sequence that is never decremented. Refunding a failed generation frees a slot but never reissues a number, so a retry cannot overwrite an earlier generation's stored image.
- A generation that fails for **any** reason — image generation, image storage, target download, or result evaluation — refunds its slot. Its consumed evaluation stays consumed, so a retry re-evaluates the prompt first.
- Learning Mode computes an Efficiency score (see Efficiency Score) and shows it with Prompt Quality, Result Quality, prompt tokens, evaluations used, and generations. It does not compute a Final score.
- Selected generation: the one with the highest Result Quality (ties go to the earlier one). Result Quality and Prompt Quality come from it.

If the prompt fails:

```text
Prompt Score: 64

Your prompt needs more detail.

Needs improvement:
• Describe where the main subject appears
• Mention the time of day
• Include the important lighting

[ Edit Prompt ]
```

If the prompt passes:

```text
Prompt Score: 84

✓ Ready to generate

[ Generate Image ]
```

---

## Game Mode

Two players receive the same challenge. Each player gets exactly **1 image generation**.

Prompts are **never blocked** in Game Mode. The Prompt Evaluator runs **in parallel** with image generation (do not wait for it before generating).

```text
User Prompt
      │
      ├──────────────► Prompt Evaluator ──► Prompt Score
      │
      ▼
Image Generator
      │
      ▼
Generated Image
      │
      ▼
Result Evaluator
      │
      ▼
Result Score
```

### Game Lifecycle

- **Identity**: every player signs in to an account (see Accounts), and the account id is the `userId` sent with every game request along with the account's display name.
- **Create**: `POST /api/games` with optional `challengeId` (random challenge if omitted). Creator joins as player 1. `status = waiting`.
- **Join**: `POST /api/games/:id/join`. Second player joins. `status = active`. A third join returns `409`.
- **Generate**: allowed only while `status = active` and the player has not generated yet. Enforce this **atomically** in MongoDB (conditional update that reserves the slot) so double clicks cannot generate twice. The attempt is submitted automatically once its generation and evaluations finish. If image generation fails, release the slot so the player can try again. If the image succeeded but the parallel prompt evaluation failed, the slot stays used: calling generate again only re-scores the stored image's prompt, so a provider hiccup can never buy a second image. The UI surfaces this as a "Score my prompt again" action rather than a dead end.
- **Complete**: when both players have submitted, the backend computes scores, sets `winnerUserId`, and sets `status = completed`.
- **Polling**: clients poll `GET /api/games/:id` every 2 seconds. Opponent prompts and images are hidden until `completed`; before that only whether the opponent has finished is shown.
- **Player ids stay private.** Since a `userId` is the only thing identifying a player, it is never serialized: a game view marks each player `isYou` and reports the winner as `you` / `opponent` / `draw`. Otherwise anyone who saw an opponent's id in a response could ask for their view and receive their prompt and image capability.
- **Invite**: the creator shares the URL `#/game/:id`. Opening it calls join automatically, so the MVP needs no matchmaking or lobby.

### Winner

Highest final score wins. Tie-breaks in order: higher Result Quality, then fewer prompt tokens. If still tied, `winnerUserId = null` (draw).

---

## Image Generation

Use Meta Muse Image via the Meta Model API, configured through `META_API_BASE_URL` and `META_IMAGE_MODEL`.

Rules:

- **Text-to-image only.** Never pass the target image (or any image) to the generator. Do not use edit/compose endpoints.
- Disable Muse Image's built-in image search, web search, and shell tools (`tool_enablement`), so a result depends only on the prompt rather than references the model found on the web.
- Request the supported aspect ratio closest to the target's (stored `width`/`height` on the challenge), passed as Muse Image's `size` `"WxH"` string. This keeps composition comparisons fair.
- Ask for `output_format: png`, since the stored bytes are served straight to the browser and re-read by the result evaluator.
- 1 image per call.
- Provider failures, timeouts, and safety refusals do **not** consume a generation. Return an error and release the reserved slot.
- Prefer inline `b64_json` responses. A response that carries a URL instead is only fetched when it is `https` on the configured `META_API_BASE_URL` host, so a redirected or compromised endpoint cannot make the backend fetch internal addresses.
- Download the returned image immediately and store it in Dropbox at `DROPBOX_GENERATED_FOLDER/{attemptId}/{generationNumber}.png`. Provider URLs may expire.

Service interface (keep provider logic behind it so another provider can be swapped in):

```text
generateImage(prompt, aspectRatio) → GeneratedImage
```

```json
{
  "imageBytes": "...",
  "mimeType": "image/png",
  "provider": "meta",
  "model": "...",
  "generationTimeMs": 0
}
```

Generation may take tens of seconds. The UI must show a loading state.

---

## Result Evaluator

The Result Evaluator receives:

```text
Target Image
+
Generated Image
+
Challenge Rubric
```

For every rubric criterion it returns an integer score from 0 to 100, plus short feedback.

```json
{
  "criteria": [
    { "id": "criterion_1", "score": 100 },
    { "id": "criterion_2", "score": 85 },
    { "id": "criterion_3", "score": 90 },
    { "id": "criterion_4", "score": 70 },
    { "id": "criterion_5", "score": 80 },
    { "id": "criterion_6", "score": 95 }
  ],
  "feedback": "The main subject and nighttime environment match closely, but the generated image is missing some of the blue pavement reflections."
}
```

Validation: exactly one entry per rubric id.

```python
result_quality = sum(c.weight * (c.score / 100) for c in criteria)
```

Do not rely on one unexplained LLM-generated similarity number.

---

## Token Counting

Count prompt tokens in the backend with one fixed tokenizer for everyone (e.g. `tiktoken` with the `o200k_base` encoding, or its JS port). Count the user's prompt text only. Do not use provider-reported usage, which differs by provider and includes system prompts.

---

## Efficiency Score (both modes)

Computed in backend code. No AI evaluator. One function for both modes.

```python
BASELINE_TOKENS = 50

token_penalty = min(15, max(0, total_prompt_tokens - BASELINE_TOKENS) // 5)
evaluation_penalty = min(20, failed_evaluations * 5)

efficiency = 100
efficiency -= (generation_count - 1) * 25
efficiency -= evaluation_penalty
efficiency -= token_penalty
efficiency = max(0, efficiency)

if selected_result_quality < 60:
    efficiency = 0
```

- `total_prompt_tokens`: sum across all generations in the attempt.
- `failed_evaluations`: Learning Mode evaluations that did not pass. Always 0 in Game Mode.
- `generation_count`: up to 3 in Learning Mode, always 1 in Game Mode.

Resulting behavior:

```text
Game Mode      → 85 to 100, driven only by prompt tokens
Learning Mode  → generations cost most (25 each after the first),
                 failed evaluations cost a little (5 each, max 20),
                 prompt length costs least (max 15)
```

The quality gate prevents exploits: a terrible result does not earn an efficiency bonus for a short prompt.

> **First achieve a useful result. Then optimize resource usage.**

---

## Resource Usage

Show directly measurable metrics:

```text
Prompt Tokens
Generations (Learning Mode)
Prompt Evaluations (Learning Mode)
```

Only generations, failed evaluations, and tokens affect the Efficiency Score. Also log total API calls per attempt for debugging, but do not score them (players do not control evaluator calls).

Optionally display **Estimated / Relative Resource Usage**. Do not claim an exact energy or carbon measurement unless the provider exposes reliable data.

---

## Final Game Score (Game Mode only)

```python
final_score = (
    result_quality * 0.70
    + prompt_quality * 0.15
    + efficiency * 0.15
)
```

Store all scores unrounded. Round to integers only for display.

---

## MongoDB

Collections:

```text
challenges
attempts
games
```

Use MongoDB-generated `ObjectId`s for `_id`. The string ids in examples below are illustrative.

Indexes:

```javascript
db.challenges.createIndex({ "target.imageHash": 1 }, { unique: true });
db.attempts.createIndex({ challengeId: 1 });
db.attempts.createIndex({ gameId: 1 });
```

---

## `challenges` Collection

```json
{
  "_id": "challenge_001",

  "type": "image",

  "difficulty": "medium",

  "target": {
    "dropboxFileId": "abc123",
    "dropboxPath": "/PromptForward/Challenges/SHA256_HASH_HERE.png",
    "imageHash": "SHA256_HASH_HERE",
    "mimeType": "image/png",
    "width": 1536,
    "height": 1024
  },

  "rubric": {
    "criteria": [
      { "id": "criterion_1", "category": "subject", "description": "yellow umbrella", "weight": 20, "critical": true },
      { "id": "criterion_2", "category": "composition", "description": "umbrella near center", "weight": 15, "critical": true }
    ]
  },

  "analysis": {
    "provider": "openai",
    "model": "MODEL_NAME",
    "version": 1,
    "analyzedAt": "TIMESTAMP"
  },

  "createdAt": "TIMESTAMP",
  "updatedAt": "TIMESTAMP"
}
```

### Difficulty

Every challenge carries a `difficulty` of `easy`, `medium`, or `hard`, chosen by whoever adds the target image (the seed folder it came from, or the upload request). It is descriptive only: it never changes scoring, generation limits, or the rubric. It exists so a player can pick a target that matches their level — easy targets are a single clear subject, medium adds a setting and specific lighting, hard has multiple interacting subjects, an unusual style, or a precise composition.

`GET /api/challenges` returns `difficulty` on every summary and accepts an optional `?difficulty=` filter. A random game picks from the requested difficulty when one is given.

`analysis.version` is a constant in code (`ANALYSIS_VERSION`). Bump it when the analyzer prompt or schema changes; `createChallenge` re-analyzes any challenge with an older version and updates it in place.

---

## `attempts` Collection

One document is one user's attempt at a challenge. Generations are embedded (max 3 in Learning Mode, 1 in Game Mode). The example below is a Learning Mode attempt.

```json
{
  "_id": "attempt_123",

  "challengeId": "challenge_001",
  "gameId": null,
  "userId": "player_uuid_1",
  "displayName": "Kris",

  "mode": "learning",
  "status": "submitted",

  "promptEvaluations": [
    { "prompt": "A yellow umbrella in the rain", "promptTokens": 7, "promptQuality": 48, "passed": false, "createdAt": "TIMESTAMP" },
    { "prompt": "A realistic nighttime photograph...", "promptTokens": 74, "promptQuality": 83.2, "passed": true, "createdAt": "TIMESTAMP" },
    { "prompt": "A realistic street-level photograph...", "promptTokens": 91, "promptQuality": 90.4, "passed": true, "createdAt": "TIMESTAMP" }
  ],

  "generations": [
    {
      "number": 1,
      "prompt": "A realistic nighttime photograph...",
      "promptEvaluation": {
        "criteria": [ { "id": "criterion_1", "status": "covered" } ],
        "craftsmanship": { "clarity": 90, "relevantSpecificity": 84, "spatialClarity": 80, "conciseness": 92 },
        "targetCoverage": 82,
        "craftsmanshipScore": 86,
        "promptQuality": 83.2,
        "feedback": "..."
      },
      "usage": { "promptTokens": 74 },
      "output": {
        "type": "image",
        "dropboxPath": "/PromptForward/Generated/attempt_123/1.png",
        "provider": "meta",
        "model": "...",
        "generationTimeMs": 0
      },
      "resultEvaluation": {
        "criteria": [ { "id": "criterion_1", "score": 100 } ],
        "resultQuality": 84,
        "feedback": "..."
      },
      "createdAt": "TIMESTAMP"
    },
    {
      "number": 2,
      "prompt": "A realistic street-level photograph...",
      "promptEvaluation": {
        "targetCoverage": 91,
        "craftsmanshipScore": 89,
        "promptQuality": 90.4,
        "feedback": "..."
      },
      "usage": { "promptTokens": 91 },
      "output": { "type": "image", "dropboxPath": "/PromptForward/Generated/attempt_123/2.png" },
      "resultEvaluation": { "resultQuality": 92, "feedback": "..." },
      "createdAt": "TIMESTAMP"
    }
  ],

  "selectedGeneration": 2,

  "scores": {
    "resultQuality": 92,
    "promptQuality": 90.4,
    "efficiency": 55,
    "final": null
  },

  "createdAt": "TIMESTAMP"
}
```

Check: 2 generations → −25; 1 failed evaluation → −5; 165 total tokens → −15. Efficiency = 100 − 25 − 5 − 15 = 55. No final score in Learning Mode.

- `mode`: `learning | game`
- `status`: `in_progress | submitted`
- `promptEvaluations` (Learning Mode): every evaluation run, `{ prompt, promptTokens, ...promptEvaluation, passed, createdAt }`. The gate checks the last entry.
- `scores` is set once the attempt is submitted. `final` is only computed in Game Mode.

---

## `games` Collection

```json
{
  "_id": "game_123",
  "challengeId": "challenge_001",
  "players": [
    { "userId": "player_uuid_1", "displayName": "Kris", "attemptId": "attempt_123" },
    { "userId": "player_uuid_2", "displayName": "Sam", "attemptId": "attempt_124" }
  ],
  "winnerUserId": "player_uuid_1",
  "status": "completed",
  "createdAt": "TIMESTAMP",
  "completedAt": "TIMESTAMP"
}
```

```text
status = waiting | active | completed
```

---

## Dropbox

Dropbox stores target images and generated images. MongoDB stores references.

```text
Dropbox
├── /PromptForward/Challenges/{easy|medium|hard}/{imageHash}.{ext}
└── /PromptForward/Generated/{attemptId}/{n}.png

MongoDB
├── Dropbox file references
├── Image hash, dimensions
├── Challenge rubric
├── Analysis metadata
├── Attempts
└── Scores
```

Target images live in a difficulty subfolder, which is what the seed script reads to label each challenge. Images sitting directly in the challenges folder are treated as `medium`.

Naming target files by hash makes uploads idempotent (upload with overwrite off; if the file exists, reuse it).

**Serving images to the browser**: Dropbox paths are not public URLs. The backend exposes image endpoints (see routes) that stream the file from Dropbox. Alternatively return Dropbox temporary links (valid ~4 hours), but never store them in MongoDB.

---

## Adding a Target Image

```text
createChallenge(imageBytes, difficulty)

1. Calculate SHA-256 hash
2. Search MongoDB for target.imageHash
3. If found and analysis.version == ANALYSIS_VERSION: return it
4. Read image dimensions and mime type
5. Send image to Challenge Analyzer
6. Validate and normalize rubric (assign ids, weights sum to 100)
7. Store image in Dropbox as {imageHash}.{ext} if not already there
8. Insert (or update, if re-analyzing) the challenge in MongoDB
9. On duplicate-key error (concurrent insert): fetch and return the existing challenge
10. Return challenge
```

Analyzing before uploading means a failed analysis leaves no orphaned files.

```javascript
async function createChallenge(imageBytes) {
  const imageHash = sha256(imageBytes);

  const existing = await challenges.findOne({ "target.imageHash": imageHash });
  if (existing && existing.analysis.version === ANALYSIS_VERSION) return existing;

  const { width, height, mimeType } = readImageMeta(imageBytes);
  const rubric = validateAndNormalizeRubric(await analyzeChallenge(imageBytes, mimeType));
  const dropboxFile = await storeTargetImage(imageBytes, imageHash, mimeType);

  const now = new Date();
  const doc = {
    type: "image",
    target: {
      dropboxFileId: dropboxFile.id,
      dropboxPath: dropboxFile.path,
      imageHash, mimeType, width, height
    },
    rubric,
    analysis: {
      provider: "openai",
      model: config.openai.challengeAnalyzerModel,
      version: ANALYSIS_VERSION,
      analyzedAt: now
    },
    updatedAt: now
  };

  if (existing) {
    await challenges.updateOne({ _id: existing._id }, { $set: doc });
    return { ...existing, ...doc };
  }

  try {
    const { insertedId } = await challenges.insertOne({ ...doc, createdAt: now });
    return { _id: insertedId, ...doc, createdAt: now };
  } catch (err) {
    if (isDuplicateKeyError(err)) {
      return challenges.findOne({ "target.imageHash": imageHash });
    }
    throw err;
  }
}
```

---

## Backend Service Structure

```text
backend/
│
├── config                 (env loading + validation, model names)
│
├── services/
│   ├── openai/
│   │   ├── challengeAnalyzer
│   │   ├── promptEvaluator
│   │   └── resultEvaluator
│   │
│   ├── meta/
│   │   └── imageGenerator
│   │
│   ├── dropbox/
│   │   └── imageStorage
│   │
│   └── scoring/
│       ├── tokenCounter
│       ├── promptScore
│       ├── resultScore
│       ├── efficiencyScore
│       └── finalScore
│
├── models/
│   ├── Challenge
│   ├── Attempt
│   └── Game
│
├── routes/
│   ├── challenges
│   ├── learning
│   ├── games
│   └── images
│
└── scripts/
    └── seedChallenges
```

Write unit tests for everything in `services/scoring/`, using the worked examples in this document as test cases.

---

## Accounts

Each player has an account so stats are theirs rather than their browser's.

- `users` collection: `{ _id, username (unique, lowercased), displayName, passwordHash, progress: { xp, attempts, generations, streak, lastPlayedDay }, createdAt }`.
- Passwords are hashed with bcrypt; the plain password is never stored or logged. Usernames are 3-32 characters, passwords at least 8.
- Sign-up and login return an opaque session token (`secrets.token_urlsafe`) stored in a `sessions` collection keyed by the token hash. The client keeps it in `localStorage` and sends `Authorization: Bearer <token>`; logout deletes the session.
- The account id is the `userId` used by Learning attempts and Battle games, so a player's history is tied to the account rather than a generated UUID.
- Progress lives on the user document and is updated server-side by `POST /api/auth/progress`, which applies the same rules as before (score → XP, streak on consecutive UTC days, generations counted) and returns the new totals. It stays cosmetic and never feeds scoring.
- This is hackathon-grade auth: no email verification, password reset, or OAuth. Sessions do not expire.

---

## API Routes

```http
POST /api/auth/signup                         { username, password, displayName? } → token + user
POST /api/auth/login                          { username, password } → token + user
POST /api/auth/logout                         ends the session
GET  /api/auth/me                             signed-in user + progress
POST /api/auth/progress                       { score, generations } → updated progress

GET  /api/challenges                          list challenges (id + image URL only)
GET  /api/challenges/:id                      challenge WITHOUT rubric
GET  /api/challenges/:id/image                target image bytes
POST /api/challenges                          dev only: upload a target image

POST /api/learning/attempts                   { challengeId, userId } → attempt
GET  /api/learning/attempts/:id
POST /api/learning/attempts/:id/evaluate      { prompt } → evaluation + passed
POST /api/learning/attempts/:id/generate      { prompt } → 409 unless gate passed

POST /api/games                               { userId, displayName, challengeId? }
POST /api/games/:id/join                      { userId, displayName }
GET  /api/games/:id                           opponent details hidden until completed
POST /api/games/:id/generate                  { userId, prompt } → one per player

GET  /api/attempts/:id/generations/:n/image?token=   generated image bytes
```

**Never send the rubric to the client.** It is effectively the answer key.

Prompts are capped at 2000 characters (`422` beyond) so a single request cannot run up tokenizer, storage, and provider cost.

Generated images are as private as the attempt they belong to. Each attempt gets an unguessable `imageToken` when it is created; the image route requires it. The token reaches a client only inside a view it is allowed to see, so an opponent receives it once the game is `completed` and never before. Image access therefore rests on the token rather than the session, and a guessed attempt id or `userId` reveals nothing.

Do not overbuild the API.

---

## Splash and Sign-In UI

Every load opens on a full-screen splash: the logo mark, the wordmark, and the tagline on the eggshell background, fading in and clearing itself after ~1.6s (or on click). It also covers the session restore, so a returning player never sees a flash of the login form. Afterwards a signed-out player gets a centered sign-in card — username, password, one button, and a link that toggles between logging in and creating an account — and a signed-in player goes straight to the lobby, with their name, avatar, and a log-out link in the top-right of the header.

---

## Home Screen UI

A game-style lobby, not a grid of every challenge. The player sets a difficulty once and each mode then draws a random target at that difficulty.

```text
┌─────────────────────────────────────┐
│ [avatar] Kris            12 targets │
│                                     │
│     Difficulty  [Easy][Med][Hard]   │
│                                     │
│        ┌───────────────────┐        │
│        │         ?         │        │
│        │  hidden until you │        │
│        │       start       │        │
│        └───────────────────┘        │
│                                     │
│   [  Learning  ]     [  Battle  ]   │
└─────────────────────────────────────┘
```

- Difficulty is a player setting stored in the browser; it defaults to `easy`.
- The target is never shown on the lobby: the card shows a static illustrative example of that difficulty (bundled in `frontend/public/examples/`), never a real target, so nobody can pre-read the image and pre-write a prompt. Inside Learning and Battle the target is visible as the reference to describe.
- **Learning** starts a solo attempt on a random target of that difficulty, and after an attempt is scored a "Next target" button starts a fresh attempt on another random target at the same difficulty, so practice is endless without returning to the lobby.
- **Battle** creates a game and lets the server pick the random target for that difficulty, then shows the invite link.
- If a difficulty has no targets yet, both buttons are disabled with a "no targets at this difficulty" note.
- Below the buttons, a "How it works" section explains the two modes and the three score parts (result quality, prompt quality, efficiency) so a first-time player needs no instructions.

Player progress strip: the lobby shows three outlined pills above the difficulty picker — a day streak, grams of CO2e saved, and an XP level with a title (Novice → Prompt Master). Progress belongs to the signed-in account and lives on the user document in MongoDB: each finished attempt adds its score as XP, extends the streak when it is the next calendar day, and counts the generations used; the saving is the generations not spent against a three-per-target baseline at a rough 4.2 g CO2e per generation. The client posts finished attempts to `POST /api/auth/progress` and renders the returned totals, so stats follow the player to any browser. It is a motivational display only and never feeds scoring. The pills lift on hover and their icons animate continuously (flame flickers, leaf sways, trophy shines), as does the logo arrow; all of it stops under `prefers-reduced-motion`.

Prompt composer: both modes write prompts in a ChatGPT-style composer — one rounded white container outlined in dark that holds an auto-growing borderless textarea with its action buttons inside on the bottom right (Learning: a ghost "Evaluate" button plus a circular blue send button that is enabled once the prompt passes; Battle: the send button alone). Enter submits, Shift+Enter adds a newline, and the send button shows a spinner while a generation is running. Interaction polish: hover/press feedback on buttons and difficulty tabs, and results fade up on reveal with the winner card popping once.

Battle result screen: while a game is active no scores are shown — after a player generates, the panel only confirms the image is in and says scores are revealed once the opponent finishes. When the game completes, both players' generated images are shown side by side in outlined cards with their score breakdown and prompt, and the winner's card is highlighted in green with a "winner" label (a draw is labelled below the cards).

Visual style: minimal and flat on an eggshell-white background (`#f4f1ea`), dark text, thin borders, no gradients or shadows. The page content sits on an eggshell card outlined in dark, and the area around it tiles a light cartoon doodle pattern (`frontend/public/doodles.svg`: sparkles, stars, squiggles, picture frames) in Google's palette to signal creativity without competing with the text. Accents use Google's palette (blue `#1a73e8`, red `#ea4335`, yellow `#f9ab00`, green `#34a853`): a cartoon speech-bubble-and-spark logo mark, a two-tone "Prompt/Forward" wordmark in Fredoka, colored difficulty tabs, and solid mode buttons (blue Learning, yellow Battle) with the same dark outline as the logo. The player name and avatar sit in the top-right of the header. Body type is Inter from Google Fonts at a large base size, and corners are rounded, so the app reads at a glance for all ages.

---

## Learning Mode UI

```text
┌─────────────────────────────────────┐
│            TARGET IMAGE             │
│                                     │
│              [image]                │
│                                     │
├─────────────────────────────────────┤
│ Write a prompt                      │
│                                     │
│ [                                 ] │
│ [                                 ] │
│                                     │
│          [ Evaluate Prompt ]        │
└─────────────────────────────────────┘
```

Editing the prompt after a pass disables **Generate** until it is re-evaluated.

If it fails:

```text
Prompt Quality: 64

Needs improvement:

• Describe where the main subject appears
• Mention the time of day
• Include the important lighting

[ Edit Prompt ]
```

If it passes:

```text
Prompt Quality: 84

✓ Ready to generate

[ Generate Image ]
```

---

## Learning Result UI

```text
TARGET                        YOUR RESULT

[ image ]                     [ image ]


Prompt Quality                    84
Result Quality                    89
Efficiency                        91

Prompt Tokens                     72
Prompt Evaluations                 2
Generations                        1


Feedback

You captured the subject and environment well.
The largest difference was composition.
```

---

## Game Mode UI

```text
TARGET IMAGE

[ image ]


One generation. Make it count.      Opponent: writing...

Prompt:

[                                   ]
[                                   ]

              [ Generate ]
```

---

## Game Results UI

```text
PLAYER 1                         PLAYER 2

[ image ]                        [ image ]


Result Quality       91          Result Quality       89

Prompt Quality       86          Prompt Quality       80

Efficiency           96          Efficiency          100

Prompt Tokens        74          Prompt Tokens        43


FINAL                91          FINAL                89


              PLAYER 1 WINS
```

Check:
- Player 1: 74 tokens → penalty 4 → efficiency 96. Final = 63.7 + 12.9 + 14.4 = 91.0
- Player 2: 43 tokens → penalty 0 → efficiency 100. Final = 62.3 + 12.0 + 15.0 = 89.3 → 89

---

## Future Text Mode

Do **not** build this until image mode works.

The architecture should support `"type": "text"` alongside `"type": "image"`:

```json
{
  "_id": "challenge_text_001",
  "type": "text",
  "target": {
    "task": "Write a concise product description for a reusable water bottle aimed at college students."
  },
  "rubric": {
    "criteria": [
      { "id": "criterion_1", "category": "audience", "description": "targets college students", "weight": 25, "critical": true },
      { "id": "criterion_2", "category": "format", "description": "short product description", "weight": 25, "critical": true }
    ]
  }
}
```

The pipeline stays the same:

```text
Challenge → Prompt → Prompt Evaluation → Generation → Result Evaluation → Efficiency → Final Score
```

Only the generator and result evaluator change. For now, just keep `type` checks at the generator and result-evaluator boundaries; do not implement text mode.

---

## MVP Priorities

### Must Have

- Env validation at startup
- MongoDB connection
- Dropbox connection (refresh-token auth)
- OpenAI connection
- Meta connection
- Seed script for target images
- Image deduplication using SHA-256
- Automatic Challenge Analyzer with rubric validation
- Stored challenge rubric
- Prompt Evaluator
- Learning Mode prompt gate (server-enforced)
- Prompt feedback
- Image generation + generated image storage
- Result Evaluator
- Game Mode (create, join, generate, poll)
- Generation limits enforced atomically (1 in Game Mode, 3 in Learning Mode)
- Token tracking
- Generation tracking
- Efficiency score (both modes)
- Final score (Game Mode)
- Results screen
- Unit tests for scoring

### Nice to Have

- Login
- Saved history
- Simple leaderboard
- Text-generation challenge

### Do Not Build Yet

- Agent battles
- Matchmaking
- Friends
- Tournaments
- Advanced skill profiles
- Exact carbon calculations
- Advanced personalization
- User-created challenges
- WebSockets (polling is enough)

---

## MVP Success Criteria

The project is successful when the demo can show both flows.

### Learning Mode

```text
Target image
    ↓
Write weak prompt
    ↓
Automatic evaluation
    ↓
Receive useful feedback
    ↓
Improve prompt
    ↓
Pass evaluation
    ↓
Generate image
    ↓
Compare target vs result
```

> **PromptForward catches what is missing before the user wastes an image generation.**

### Game Mode

```text
Same target image
    ↓
Two different prompts
    ↓
Generate results
    ↓
Evaluate result quality
    ↓
Measure prompt quality
    ↓
Measure resource usage
    ↓
Calculate final scores
    ↓
Winner
```

> **The winner is rewarded for producing a strong result efficiently, not simply for writing the shortest prompt.**

---

## One-Sentence Pitch

**PromptForward turns AI generation tasks into interactive challenges that teach users to get better results with clearer prompts and fewer wasted generations.**
