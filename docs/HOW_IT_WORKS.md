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

### Final score (`final_score.py`, Battle only)

```text
final = 0.70 × resultQuality + 0.15 × promptQuality + 0.15 × efficiency
```

Winner: highest `final`; ties break on `resultQuality`, then on fewer prompt tokens; a full tie is
a draw.

---

## 2. Image generation route

`POST /api/learning/attempts/{id}/generate` (Learning) and
`POST /api/games/{id}/generate` (Battle). Both go through `backend/app/services/attempts.py`, so
the rules below hold in either mode.

1. **Reserve a slot** — `reserve_generation` does one atomic MongoDB `find_one_and_update`:
   `reservedGenerations < limit` (3 in Learning, 1 in Battle) and, in Learning, the gate below.
   The generation number comes from `generationSequence`, which only grows, so a refunded slot
   never reuses a number an in-flight generation is writing to.
2. **Server-side evaluation gate (Learning)** — the same update requires that the most recent
   evaluation passed, was for exactly this prompt, and has not already been consumed by an earlier
   generation. A client cannot skip evaluation or reuse one passing evaluation twice.
3. **Generate** — Meta Muse Image, text-to-image only; the target image is never sent to the
   generator. The aspect ratio is the supported ratio closest to the target's.
4. **Store** — the PNG goes to Dropbox and is served back through `/api/images/...`.
5. **Evaluate the result** — the target and the generation are sent to the result evaluator, which
   scores every rubric criterion.
6. **Score and submit** — `submit_attempt` recomputes all three scores from the stored generations
   and marks the attempt `submitted`.

Failure handling: every provider error (generation, storage, result scoring) surfaces as
`GenerationFailed`, the reserved slot is refunded with `release_generation`, and the route returns
502 — **a failed generation never costs the player a try**. The exception is a failure *after* the
image is committed: the image is kept and the player is offered "score my prompt again", which
does not consume a second generation.

---

## 3. Learning Mode feedback UI

`frontend/src/components/LearningMode.tsx`, `Composer.tsx`, `EcoPrompt.tsx`, `XraySlider.tsx`.

### The arrow is the only control

There is no Evaluate button. The circular send arrow inside the composer carries the verdict:

| Arrow | Meaning | Clicking it |
|---|---|---|
| Blue | Prompt not evaluated (or edited since) | Evaluates the prompt |
| Red | Evaluated and failed (`promptQuality < 70` or a critical criterion missing) | Evaluates again |
| Green | Evaluated and passed | Generates the image |

Editing the prompt returns the arrow to blue, so generation always follows a fresh evaluation of
the exact text being generated — the same rule the server enforces. If generation fails, the
client also clears the passing evaluation so the next press re-evaluates instead of retrying
against a consumed gate.

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
