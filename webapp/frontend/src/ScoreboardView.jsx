import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner, Loading } from './ui.jsx'

function Pool({ pool }) {
  if (!pool || !pool.possible) return <span className="na">—</span>
  // graded is only ever set on the user's own pool; 0 means no picks were saved that season,
  // which reads as a losing "0/2235 0%" if we don't call it out separately.
  if (pool.graded === 0) return <span className="na">no picks</span>
  return (
    <span className="pool-cell">
      {pool.earned}<span className="muted">/{pool.possible}</span>
      <span className="pool-pct">{Math.round((100 * pool.earned) / pool.possible)}%</span>
    </span>
  )
}

export default function ScoreboardView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(() => {
    setError(null)
    setData(null)
    api.scoreboard().then(setData).catch(setError)
  }, [])

  useEffect(load, [load])

  if (error) return <div className="card"><ErrorBanner error={error} onRetry={load} /></div>
  if (!data) return <div className="card"><Loading /></div>

  const first = data.first_vegas_season
  const modern = data.seasons.filter((r) => r.season >= first)
  const rows = [...(showAll ? data.seasons : modern)].reverse()

  const avg = (list, get) => {
    const vals = list.map(get).filter((v) => v != null)
    return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : '—'
  }
  const poolPct = (get) => {
    const vals = modern.map(get).filter(Boolean)
    if (!vals.length) return '—'
    if (vals.every((p) => p.graded === 0)) return 'no picks yet'
    const earned = vals.reduce((a, p) => a + p.earned, 0)
    const possible = vals.reduce((a, p) => a + p.possible, 0)
    return possible ? `${Math.round((100 * earned) / possible)}%` : '—'
  }

  return (
    <div>
      <div className="card">
        <h2>Confidence pool</h2>
        <p className="muted">
          The office-pool game the "Your pick" column plays: each week every game is worth its
          confidence rank, and you collect those points when you pick the winner. Each model plays
          the same game by ranking the week by its own confidence, so these numbers are directly
          comparable. Weekly schedules only exist from {first} on.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Season</th>
                <th className="col-elo">Elo</th>
                <th className="col-vegas">Vegas</th>
                <th className="col-combined">Combined</th>
                <th>Your picks</th>
              </tr>
            </thead>
            <tbody>
              {modern.slice().reverse().map((r) => (
                <tr key={r.season}>
                  <td>{r.season}</td>
                  <td className="col-elo"><Pool pool={r.elo_pool} /></td>
                  <td className="col-vegas"><Pool pool={r.vegas_pool} /></td>
                  <td className="col-combined"><Pool pool={r.combined_pool} /></td>
                  <td><Pool pool={r.user_pool} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ marginTop: 14 }}>
          Share of available points — Elo: <strong>{poolPct((r) => r.elo_pool)}</strong>,
          {' '}Vegas: <strong>{poolPct((r) => r.vegas_pool)}</strong>,
          {' '}Combined: <strong>{poolPct((r) => r.combined_pool)}</strong>,
          {' '}You: <strong>{poolPct((r) => r.user_pool)}</strong>
        </p>
      </div>

      <div className="card">
        <h2>Brier points</h2>
        <p className="muted">
          The original game's scoring rule, which rewards a probability for being both correct and
          confident. Only a model produces probabilities, so your picks do not appear here. From{' '}
          {first} the benchmark is the devigged closing Vegas line; before that it is
          FiveThirtyEight's own published Elo forecast.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Season</th>
                <th className="col-elo">This app's Elo</th>
                <th className="col-vegas">Benchmark</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.season}>
                  <td>{r.season}</td>
                  <td className="col-elo">{r.elo_points}</td>
                  <td className="col-vegas">
                    {r.vegas_points ?? r.fte_points ?? <span className="na">—</span>}
                  </td>
                  <td className="muted">
                    {r.vegas_points != null ? 'Vegas' : r.fte_points != null ? '538 Elo' : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ marginTop: 14 }}>
          Since {first} — this app's Elo averages <strong>{avg(modern, (r) => r.elo_points)}</strong> points
          a season against Vegas's <strong>{avg(modern, (r) => r.vegas_points)}</strong>.
        </p>
        <button className="secondary" onClick={() => setShowAll((v) => !v)}>
          {showAll ? `Show ${first}+ only` : 'Show all seasons back to 1920'}
        </button>
      </div>
    </div>
  )
}
