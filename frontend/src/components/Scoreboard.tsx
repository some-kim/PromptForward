import type { Attempt } from '../api'
import { round } from '../format'

export function Scoreboard({ attempt, showFinal }: { attempt: Attempt; showFinal?: boolean }) {
  const scores = attempt.scores
  const usage = attempt.usage

  return (
    <dl className="scoreboard">
      <div>
        <dt>Prompt Quality</dt>
        <dd>{round(scores?.promptQuality)}</dd>
      </div>
      <div>
        <dt>Result Quality</dt>
        <dd>{round(scores?.resultQuality)}</dd>
      </div>
      <div>
        <dt>Efficiency</dt>
        <dd>{round(scores?.efficiency)}</dd>
      </div>
      <div className="spacer">
        <dt>Prompt Tokens</dt>
        <dd>{usage?.promptTokens ?? '—'}</dd>
      </div>
      {attempt.mode === 'learning' && (
        <>
          <div>
            <dt>Prompt Evaluations</dt>
            <dd>{usage?.promptEvaluations ?? '—'}</dd>
          </div>
          <div>
            <dt>Generations</dt>
            <dd>{usage?.generations ?? '—'}</dd>
          </div>
        </>
      )}
      {showFinal && (
        <div className="final">
          <dt>Final</dt>
          <dd>{round(scores?.final)}</dd>
        </div>
      )}
    </dl>
  )
}
