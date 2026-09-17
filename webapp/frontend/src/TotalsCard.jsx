import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner } from './ui.jsx'

const METHODS = [
  { id: 'vegas', label: 'Vegas total line' },
  { id: 'season', label: 'Season scoring average' },
  { id: 'recent', label: 'Recent form (last 4)' },
  { id: 'league', label: 'League average' },
]

function overUnder(total, line) {
  if (total == null || line == null) return null
  if (total > line) return 'Over'
  if (total < line) return 'Under'
  return 'Push'
}

function GameTotalCard({ game, onSaved }) {
  const [value, setValue] = useState(game.user_total ?? '')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    setValue(game.user_total ?? '')
  }, [game.game_id, game.user_total])

  const save = async () => {
    if (value === '' || Number(value) === game.user_total) return
    setSaving(true)
    setError(null)
    try {
      await api.saveTotal(game.game_id, Number(value))
      setStatus('Saved')
      setTimeout(() => setStatus(''), 2000)
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  const clear = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.clearTotal(game.game_id)
      setValue('')
      onSaved()
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  const actual = game.actual_total
  const guess = game.user_total
  const diff = actual != null && guess != null ? Math.abs(actual - guess) : null
  const actualSide = overUnder(actual, game.methods.vegas)
  const guessSide = overUnder(guess, game.methods.vegas)
  const guessedRightSide = actualSide != null && guessSide != null ? actualSide === guessSide : null

  return (
    <div className="card totals-card">
      <div className="totals-header">
        <span className="totals-label">Monday night total</span>
        <span className="muted">{game.date}{game.gametime ? ` ${game.gametime}` : ''}</span>
      </div>
      <div className="totals-matchup">{game.team2} @ {game.team1}</div>

      <div className="totals-input-row">
        <label htmlFor={`total-${game.game_id}`}>Your prediction</label>
        <input
          id={`total-${game.game_id}`}
          type="number"
          placeholder="e.g. 44"
          value={value}
          disabled={saving}
          onChange={(e) => setValue(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
        />
        <span className="muted">total points</span>
        {guess != null && (
          <button className="secondary" disabled={saving} onClick={clear}>Clear</button>
        )}
        {status && <span className="status-msg">{status}</span>}
      </div>

      <ErrorBanner error={error} onRetry={() => setError(null)} />

      <div className="totals-methods-label">Predicted totals</div>
      <table className="totals-methods">
        <tbody>
          {METHODS.map((m) => (
            <tr key={m.id}>
              <td>{m.label}</td>
              <td className="totals-value">{game.methods[m.id] ?? <span className="na">—</span>}</td>
            </tr>
          ))}
          <tr className="totals-consensus">
            <td>Consensus</td>
            <td className="totals-value">{game.methods.consensus ?? <span className="na">—</span>}</td>
          </tr>
        </tbody>
      </table>

      {actual != null && (
        <div className="totals-result">
          <span><strong>Final:</strong> {actual} total points</span>
          {diff != null && <span>Your guess was off by {diff}</span>}
          {guessedRightSide != null && (
            <span className={guessedRightSide ? 'result-correct' : 'result-wrong'}>
              {guessedRightSide ? '✓' : '✗'} {actualSide} the Vegas line
            </span>
          )}
        </div>
      )}
    </div>
  )
}

export default function TotalsCard({ season, week }) {
  const [games, setGames] = useState([])
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    if (season == null || week == null) return
    setError(null)
    api.totals(season, week).then((d) => setGames(d.games)).catch(setError)
  }, [season, week])

  useEffect(load, [load])

  if (error) return <div className="card"><ErrorBanner error={error} onRetry={load} /></div>
  if (!games.length) return null

  return (
    <div className="totals-section">
      {games.map((g) => (
        <GameTotalCard key={g.game_id} game={g} onSaved={load} />
      ))}
    </div>
  )
}
