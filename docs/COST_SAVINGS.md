# Cost savings: what is counted, how, and what could be built next

PromptForward spends money on three kinds of model call: the **prompt check** (a text
model scores a prompt against the target's rubric, ~30 s), the **image generation**
(the expensive one), and the **target analysis** (a vision call that turns a target
image into its rubric). This document explains how the app avoids paying for calls it
does not need, how the numbers on the Home page are computed, and what could be built
out further for a sustainability / cost story.

## 1. Where the savings come from

| Mechanism | What happens | Call avoided |
|---|---|---|
| **Check before you generate** | A prompt is scored before an image is made. If it fails the check and the learner rewrites it instead of generating, the image call never happens. | image generation |
| **Prompt-evaluation cache** | The same prompt on the same target (same image, same rubric version, same evaluator model; whitespace ignored) is scored once and stored. Repeats are served from MongoDB. | prompt check |
| **Analyse each target once** | A target image's rubric/checklist is generated when the problem is seeded and stored on the challenge. Every attempt reuses it. | target analysis |

None of these are estimates: each one leaves a record in the database, and the
statistics below are computed from those records every time they are asked for.
There is no running counter that can drift.

## 2. How the numbers are computed

Endpoint: `GET /api/stats/savings?generationCost=0.04&evaluationCost=0.002`
(both parameters optional). Implementation: `backend/app/services/savings.py`.

Data used: the `attempts` collection (each attempt holds `promptEvaluations[]` — one
entry per prompt check with `prompt` and `passed` — and `generations[]` — one entry
per image made with its `prompt`), the `prompt_evaluations` collection (the cache,
one document per distinct prompt+target with a `hits` counter), and `challenges`
(one document per target image, with `analysis` once analysed).

```
promptChecks       = sum over attempts of len(promptEvaluations)

blockedGenerations = sum over attempts of
                       count(e in promptEvaluations
                             where e.passed != true
                             and normalize(e.prompt) not in { normalize(g.prompt) for g in generations })

generations        = sum over attempts of len(generations)

cachedEvaluations  = number of documents in prompt_evaluations   (distinct prompts scored by the model)
cacheHits          = sum of prompt_evaluations.hits              (repeats served without a model call)

analyzedTargets    = number of challenges with an analysis

estimatedSavedUsd  = blockedGenerations * generationCost + cacheHits * evaluationCost
estimatedSpentUsd  = generations * generationCost + cachedEvaluations * evaluationCost
savedShare         = estimatedSavedUsd / (estimatedSavedUsd + estimatedSpentUsd)
```

Two rules keep the numbers honest:

- **A failed check only counts as a skipped generation if that prompt was never
  generated.** Learning mode deliberately lets a learner generate a weak prompt after
  seeing the verdict (so they can see *why* it is weak). In that case the check did
  not save anything, so it is not counted. Prompts are compared after whitespace
  normalisation, the same way the cache keys them.
- **A cache hit is counted only when the evaluator was not called.** The counter is
  incremented atomically on lookup (`find_one_and_update` with `$inc`). If two
  requests miss at the same time, both pay for a model call and neither counts as a
  hit, even though one of them ends up returning the other's stored result.

The dollar figures are estimates: the counts are exact, but the per-call prices are
assumptions passed in by the caller (defaults `$0.04` per image, `$0.002` per prompt
check — rough list prices, adjust to the real provider bill). Target analysis is
reported as a count only and is not priced.

### Current numbers (shared team database, 2026-09-20)

| Metric | Value | Meaning |
|---|---|---|
| promptChecks | 36 | prompts scored by the evaluator (or served from cache) |
| blockedGenerations | 9 | failed prompts the learner rewrote instead of generating |
| generations | 25 | images actually paid for |
| cachedEvaluations | 7 | distinct prompt+target pairs scored by the model |
| cacheHits | 0 | repeats served from cache (counter is new; grows as people retry prompts) |
| analyzedTargets | 47 | images analysed exactly once |
| estimatedSavedUsd | $0.36 | at the default prices |
| estimatedSpentUsd | $1.01 | at the default prices |
| savedShare | 26% | of would-be spend avoided |

So far 9 of 34 would-be image generations (26%) were never paid for. Before the
"was it generated anyway" rule was added the figure was 33 of 57 (58%) — that number
was wrong and should not be quoted.

## 3. Where it shows up

- Home page: a three-cell ledger under the mode notes — *Generations skipped*,
  *Evaluations from cache*, *Est. saved (· % of spend)*. Hidden until at least one
  call has been avoided. Component: `SavingsLedger` in
  `frontend/src/components/Home.tsx`.
- The raw JSON at `/api/stats/savings` for slides or a judge demo.

Everyone who runs the app against the shared Atlas `MONGODB_URI` sees the same
numbers, because they are computed from the shared data.

## 4. What could be built out for the sustainability angle

Ordered roughly by effort.

1. **Tokens, not just dollars (small).** `count_prompt_tokens` is already stored on
   every evaluation and generation (`promptTokens`). Summing the tokens of the
   blocked prompts and adding a tokens-per-image figure for the image model gives a
   "tokens not processed" number, which converts to an energy / CO₂ estimate with a
   published per-token or per-image figure (state the source and treat it as an
   order-of-magnitude estimate, not a measurement).

2. **Per-user savings (small).** The same aggregation filtered by `userId` — "you have
   skipped 4 generations by fixing prompts first" on the progress view. This turns
   cost saving into a learning incentive, which fits the product better than a
   site-wide total.

3. **Per-attempt cost line (small).** Show "this attempt: 1 check, 0 images, $0.002"
   in the result panel, next to the existing efficiency score. Makes the saving
   visible at the moment it happens.

4. **Track the third mechanism properly (small).** Analysis reuse is currently only a
   count of analysed targets. Recording how many attempts referenced each analysis
   (`attempts per challenge − 1` reuses) would let it be priced like the others.

5. **Persist the "blocked" event explicitly (medium).** Today "blocked" is inferred
   (failed check, prompt never generated). Recording an explicit event when a learner
   rewrites after a failed check (or when a Battle round refuses a failing prompt)
   would make the count exact rather than inferred and allow a time series
   ("savings this week").

6. **Try the sponsor's compression model on the rubric (medium, optional).** The
   rubric checklist is sent to the evaluator on every uncached check. Compressing it
   would cut input tokens per check; measure tokens before/after on the 40 problems
   and report the delta. Worth doing only if there is time after the above — the
   checklist is small, so the saving is modest.

7. **Efficiency in the score already exists.** The final score weights
   `efficiency` at 15% (fewer generations and shorter prompts score higher), so the
   product already rewards frugal behaviour; the ledger just makes it visible.
