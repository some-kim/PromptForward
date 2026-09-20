# How PromptForward works

Implementation reference for the three pieces that decide what a player sees: the scoring
service, the image-generation route, and the Learning Mode feedback UI. `docs/MVP_SPEC.md`
remains the canonical spec; this file describes what is actually running today.

---

## 1. Scoring service

All scoring math is deterministic Python in `backend/app/services/scoring/`. The LLM only ever
produces judgments (per-criterion statuses and 0-100 criterion scores); it never produces a final
number.

### Rubric

Every challenge is analyzed once at seed time into a rubric of weighted criteria
(`weight` values sum to 100), each with a `category` and a `critical` flag. The rubric text is the
answer key and is never sent to the player.

### Prompt Quality (`prompt_score.py`)

The prompt evaluator returns, for each rubric criterion, `covered` / `partial` / `missing`, plus
four craftsmanship scores.

```text
status value      covered = 1.0, partial = 0.5, missing = 0.0
targetCoverage    Σ (criterion.weight × status value)
craftsmanship     0.30 clarity + 0.30 relevantSpecificity + 0.25 spatialClarity + 0.15 conciseness
promptQuality     0.70 × targetCoverage + 0.30 × craftsmanship
```

A prompt **passes** when `promptQuality ≥ 70` **and** no criterion marked `critical` is `missing`.
A failing prompt is returned with `needsImprovement`: category-level hints only
(e.g. "describe the main subject"), never the rubric wording.

### Result Quality (`result_score.py`)

The result evaluator scores the generated image against each rubric criterion from 0-100:

```text
resultQuality = Σ (criterion.weight × criterionScore / 100)
```

Both evaluators are validated: the response must contain exactly one entry per rubric id, no
duplicates and no extras, or the call is rejected.

### Efficiency (`efficiency_score.py`)

Deterministic, no model involved. Tokens are counted with `o200k_base`.

```text
start at 100
− 25 per generation after the first
− 5 per failed prompt evaluation      (capped at 20, Learning only)
− 1 per 5 tokens above a 50-token baseline (capped at 15)
floor at 0
if resultQuality < 60 → efficiency = 0
```

The quality gate exists so a short lazy prompt cannot score well on efficiency.

### Combined score (`final_score.py`)

```text
final = 0.70 × resultQuality + 0.15 × promptQuality + 0.15 × efficiency
```

Battle calls it the final score; Training shows the same number as **Combined**, next to the
prompt-quality and image-quality it is built from.

Winner: highest `final`; ties break on `resultQuality`, then on fewer prompt tokens; a full tie is
a draw.

---

## 1b. Difficulty levels: easy, medium, hard

Difficulty is a label on the **target image**, not on the scoring. Every challenge is analyzed,
evaluated, and scored with exactly the rules above; what changes between levels is how much a
prompt has to cover to earn those points.

### How a challenge gets its level

`scripts/seed_challenges.py` walks `DROPBOX_CHALLENGES_FOLDER`. The subfolder an image sits in
becomes its difficulty; an image directly in the root (or in any other folder) is stored as
`medium`, the default.

```text
/Challenges/easy/    → easy
/Challenges/medium/  → medium
/Challenges/hard/    → hard
/Challenges/*.jpg    → medium (default)
```

The level is written once on the challenge document and travels to the client as
`challenge.difficulty`. Uploading through `POST /api/challenges` takes the same `difficulty` form
field.

### What each level asks of the player

| Level | Target image | What a passing prompt needs |
|---|---|---|
| **Easy** | One clear subject on a plain background (e.g. a single apple). | Name the subject and its obvious attributes — colour, a simple setting. Few rubric criteria carry most of the weight, so a short prompt can reach `promptQuality ≥ 70`. |
| **Medium** | A subject in a setting with specific lighting. | Cover subject **and** environment **and** lighting/mood. Weight is spread over more criteria, so a subject-only prompt usually lands `partial`/`missing` on setting and light and fails the 70 gate. |
| **Hard** | Many subjects, an unusual style or medium, and precise composition. | Cover every subject, the style, and where things sit in the frame (`spatialClarity` matters). Hard rubrics have more criteria and more of them are `critical`, so missing any one of them fails the prompt regardless of score. |

The blurbs shown in the Training lobby say the same thing in one line each ("One clear subject." /
"A subject, a setting, specific lighting." / "Many subjects, unusual style, precise composition."),
next to an example image from `frontend/public/examples/{level}.jpg`.

### Where the level is chosen

- **Training** — the difficulty tabs in the lobby pick the level; it is remembered in
  `localStorage` (`promptforward.difficulty`, default `easy`). "Start" and "Next target →" both draw
  a random challenge at that level via `GET /api/challenges?difficulty=…`.
- **Battle** — the host's current level is sent with `POST /api/games` (`difficulty`), and the
  server picks one random challenge at that level for both players. If no challenge has been
  seeded at the requested level the request fails with
  `No {level} challenges have been seeded yet`.

### Why harder feels harder without different math

Because the scores are built from the rubric, a harder target raises the bar on its own:

- **Prompt Quality** — more criteria and more `critical` flags mean more ways to miss coverage,
  and more text is needed, which pushes token count up.
- **Efficiency** — the 50-token baseline is the same at every level, so the longer prompts hard
  targets require start eating the token penalty (−1 per 5 tokens over, capped at 15), and a
  weak image (`resultQuality < 60`) still zeroes efficiency.
- **Result Quality** — the generator has to hit more criteria at once, so image quality tends to
  drop as the level rises.

Progress and Battle winners use the same combined formula at every level; there is no level
multiplier.

---

## 2. Image generation route

`POST /api/learning/attempts/{id}/generate` (Learning) and
`POST /api/games/{id}/generate` (Battle). Both go through `backend/app/services/attempts.py`, so
the rules below hold in either mode.

1. **Reserve a slot** — `reserve_generation` does one atomic MongoDB `find_one_and_update`:
   `reservedGenerations < limit` (3 in Learning, 1 in Battle).
   The generation number comes from `generationSequence`, which only grows, so a refunded slot
   never reuses a number an in-flight generation is writing to.
2. **Score the prompt** — a weak prompt is never blocked: if the prompt was not evaluated before
   the press, the route evaluates it now, so every generation carries a prompt quality to show
   beside its image quality. If the evaluator itself is unreachable the route returns 502 and
   refunds the slot, rather than spending an image on an attempt that would score zero prompt
   quality.
3. **Generate** — Meta Muse Image, text-to-image only; the target image is never sent to the
   generator. The aspect ratio is the supported ratio closest to the target's.
4. **Store** — the PNG goes to Dropbox and is served back through `/api/images/...`.
5. **Evaluate the result** — the target and the generation are sent to the result evaluator, which
   scores every rubric criterion.
6. **Score and submit** — `submit_attempt` recomputes all three scores from the stored generations
   and marks the attempt `submitted`.

Failure handling: every provider error (generation, storage, result scoring) surfaces as
`GenerationFailed`, the reserved slot is refunded with `release_generation`, and the route returns
502 — **a failed generation never costs the player a try**. The refund covers everything after the
reservation, including a cancelled request and an evaluator outage. The exception is a failure
*after* the image is committed: pressing generate again finalizes the stored image instead of
buying a second one, so scoring it does not consume a try.

---

## 3. Learning Mode feedback UI

`frontend/src/components/LearningMode.tsx`, `Composer.tsx`, `EcoPrompt.tsx`, `XraySlider.tsx`.

### The arrow is the only control

There is no Evaluate button. The circular send arrow inside the composer carries the verdict:

| Arrow | Meaning | Clicking it |
|---|---|---|
| Blue | Prompt not evaluated (or edited since) | Evaluates the prompt |
| Red | Evaluated and weak (`promptQuality < 70` or a critical criterion missing) | Generates anyway |
| Green | Evaluated and passed | Generates the image |

Editing the prompt returns the arrow to blue, so the first press always scores the exact text
being generated and the second press generates it — weak or strong. The result then shows prompt
quality, image quality, and their combined score together, which is how a weak prompt teaches.

Under the composer, a failed evaluation shows `promptQuality`, the category hints, and the
evaluator's feedback. Enter submits, Shift+Enter adds a newline, and the arrow shows a spinner
while the server is working.

### EcoPrompt card

Beside the composer, updating as you type: estimated tokens, energy (mWh), emissions (mg CO₂), and
everyday equivalences (phone charge, seconds of a 60W bulb, web searches). The estimate is
client-side and rough — 0.002 Wh per token at 0.7 g CO₂ per Wh; the backend's `o200k_base` count is
what actually scores efficiency. **Trim filler** strips hype words that cost tokens without
describing the target ("hyperrealistic", "8k", "masterpiece", "stunning", …) and reports the tokens
saved, or says there is nothing to trim.

### Attention heatmap

Each rubric criterion carries a normalized box locating it in the target image, produced by the
challenge analyzer at seed time. After an evaluation, the target is overlaid with one box per
criterion: green covered, dashed yellow partial, pulsing red missing, plus a chip legend that
highlights with its box on hover. Only the category hint travels to the client, never the rubric
description. Editing the prompt clears the overlay along with the evaluation.

### Result view

Once an image exists, the target and the generation share one frame with a drag handle (X-ray
slider) instead of sitting side by side, above the score breakdown and the result feedback.
Learning is endless: "Next target →" rolls a new random target at the same difficulty, and up to
three generations per target are available through "Try another prompt".

### Progress

When an attempt is scored, the client immediately posts `{ attemptId, score, generations }` to
`POST /api/auth/progress`. Progress is keyed by attempt id in `progress_events`, so re-reporting
the same attempt applies only the delta — logging out straight from the result screen cannot lose
it, and reopening a result cannot double-count it.
