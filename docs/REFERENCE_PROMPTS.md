# Reference prompts vs. the evaluator

Why the "model answer" attached to each problem does not pass its own problem, and what the
options are.

## How a problem is scored

Every target image goes through the same pipeline, and no human writes the answer key.

1. **Analyzer (one call per image, at seed time).** `muse-spark-1.3` looks at the image and
   returns a **rubric**: 4 to 8 criteria, each with a category (subject, action, environment,
   composition, spatial, color, lighting, style, mood), a short visually checkable description
   (e.g. "glossy bright red skin with small white speckles"), a weight, and a `critical` flag.
   Weights are normalised to sum to 100; 1 to 4 criteria are critical. The rubric is stored on
   the challenge and never shown to the player.
2. **Prompt evaluator (every time you press Evaluate).** The model reads the rubric and your
   prompt, never the image, and marks each criterion `covered` / `partial` / `missing`, plus four
   craftsmanship scores (clarity, relevant specificity, spatial clarity, conciseness).
   `promptQuality = 0.70 × coverage + 0.30 × craftsmanship`; it *passes* at ≥ 70 with no critical
   criterion missing. A failed evaluation unlocks the next hint.
3. **Image generation + result evaluator (every Generate).** `muse-image-1.0` renders your
   prompt; `muse-spark-1.3` compares the render with the target per criterion →
   `resultQuality`.
4. **Efficiency** is arithmetic: 100, minus 25 per extra generation, 5 per failed evaluation,
   and 1 per 5 tokens over a 50-token baseline; zeroed if `resultQuality < 60`.
5. `final = 0.70 × resultQuality + 0.15 × promptQuality + 0.15 × efficiency`. A problem is
   **solved** at `final ≥ 70`.

The scoring math is in `backend/app/services/scoring/`; the model only ever produces per-criterion
judgements, so the numbers are deterministic given those judgements.

## What is wrong

Each problem in `backend/curriculum/problems.json` carries a hand-written `referencePrompt`,
revealed after you solve the problem or spend all three generations. They were written as
*teaching* prompts, i.e. the shortest prompt that demonstrates the skill:

```text
A single red apple on a white background, studio photo.
```

The rubric the analyzer produced for that image, however, is much more granular:

| criterion (paraphrased)                                   | critical |
| --------------------------------------------------------- | -------- |
| one whole red apple with a short brown stem               | yes      |
| seamless pure white background, no other objects          | yes      |
| centred, large white negative space around the apple      |          |
| glossy bright red skin with small white speckles          |          |
| bright high-key soft lighting with a glossy highlight     |          |
| clean photorealistic minimalist studio photograph         |          |

Against that rubric the reference prompt is `partial` on most rows and `missing` on the
stem/speckle/negative-space details, so it scored **35** end to end. A prompt that names the
stem, the speckled glossy skin, the centred framing and the soft high-key light scored **97**.

So the player can be told "here is the model answer" and, on copying it, fail the problem.
This is a *content* mismatch, not a scoring bug: the rubric and the evaluator behave as designed;
the reference prompts were written to a different standard than the analyzer's.

Two things make it worse:

- **The analyzer decides what counts.** Reseeding an image (new analysis version, or a different
  model) can change the rubric, so a reference prompt tuned to one rubric can drift out of sync.
- **Meta vs. OpenAI.** The rubrics and judgements currently come from `muse-spark-1.3` because
  the OpenAI account is out of credits. Switching evaluators back to `gpt-4o` will not
  re-analyze existing challenges (the rubric is stored), but judgement strictness may shift a
  few points either way.

## Option A — rewrite the 40 reference prompts to rubric level

Rewrite each `referencePrompt` so that it covers every criterion in that image's stored rubric,
in the style the lesson is teaching. The seed script refreshes problem metadata for an image
that already has a current analysis **without** calling the analyzer, so this costs **zero
Meta calls** to ship. Verifying a rewrite costs one prompt-evaluation call per problem (cheap,
no image generation), or nothing if we trust the rubric read.

Rewards

- The model answer actually solves the problem, which is what players will assume. Copying it
  scores in the 90s, so the reveal reads as "this is what good looks like".
- The reference doubles as a worked example of the rubric: after a fail, the player sees
  exactly which categories a passing prompt names (stem, negative space, key light …), which is
  the lesson.
- Consistent bar across all 40: reference ≈ what "solved" requires, so difficulty labels mean
  something.

Risks

- **Loses the concision lesson.** Rubric-level prompts are 30 to 60 tokens; the `concision`
  skill (5 problems) is specifically about *not* padding. Mitigation: keep those five tight and
  accept a lower reference score there, or note in the lesson that the reference trades a few
  points for brevity.
- **Overfitting to one analysis.** Rewrites are tuned to the current rubrics. If a target is
  re-analyzed (analysis version bump, provider change), the reference can fall out of sync
  again. Mitigation: add a check to the seed script that evaluates each reference against its
  rubric and warns below 70.
- **Effort.** 40 prompts × reading a rubric each. Roughly one session; no user-facing risk.
- **Teaches "describe everything".** If every reference is exhaustive, players may learn to
  brute-force detail rather than judge what matters. Mitigation: the hints already point at
  the *skill*, not the rubric; keep them short.

## Option B — loosen the evaluator instead

Lower `SOLVED_SCORE` (70), soften how `partial` is counted, or have the analyzer emit fewer /
coarser criteria.

Rewards

- No content work; also makes the game feel less punishing for beginners.

Risks

- Changes the difficulty of *every* challenge, including random practice and Battle, not just
  the 40 problems.
- Coarser rubrics make the heat-map and "what you missed" feedback vaguer, which undermines the
  coaching.
- Re-analyzing to get coarser rubrics costs one analyzer call per image (40+ Meta calls) and
  invalidates the tuning above.

## Option C — leave as is

Rewards: nothing to do now.

Risks: the first player who solves a problem and reads the reference will notice it is shorter
and vaguer than the prompt that got them there; the first who copies it after spending three
generations will see it fail. Both undercut the "this is the model answer" framing. The reveal
could be relabelled "starting point" rather than "reference", which is honest but weaker.

## Recommendation

Option A, with two guards: keep the five `concision` references deliberately short (and say so
in their lesson text), and add a seed-time check that evaluates each reference against its
stored rubric so drift is caught the next time the manifest is reseeded.
