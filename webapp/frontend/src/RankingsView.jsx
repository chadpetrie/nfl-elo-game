import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner, Loading } from './ui.jsx'

const AVERAGE = 1505

export default function RankingsView() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setError(null)
    setRows(null)
    api.rankings().then(setRows).catch(setError)
  }, [])

  useEffect(load, [load])

  if (error) return <div className="card"><ErrorBanner error={error} onRetry={load} /></div>
  if (!rows) return <div className="card"><Loading /></div>
  if (!rows.length) return <div className="card"><div className="empty-state">No ratings available.</div></div>

  const max = Math.max(...rows.map((r) => Math.abs(r.elo - AVERAGE)))

  return (
    <div className="card">
      <h2>Power ratings</h2>
      <p className="muted">
        Every team's Elo rating after the most recent game in the data, using the parameters set on
        the Settings tab. {AVERAGE} is an average team; a 100-point edge is worth approximately
        64% win probability on a neutral field.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Team</th>
              <th>Elo</th>
              <th>vs. average</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const diff = r.elo - AVERAGE
              const width = max ? (Math.abs(diff) / max) * 50 : 0
              return (
                <tr key={r.team}>
                  <td className="muted">{r.rank}</td>
                  <td className="pred-team">{r.team}</td>
                  <td>{r.elo}</td>
                  <td>
                    <div className="elo-bar">
                      <span className="elo-bar-mid" />
                      <span
                        className={diff >= 0 ? 'elo-bar-fill pos' : 'elo-bar-fill neg'}
                        style={diff >= 0
                          ? { left: '50%', width: `${width}%` }
                          : { right: '50%', width: `${width}%` }}
                      />
                      <span className="elo-bar-label">{diff >= 0 ? '+' : ''}{Math.round(diff)}</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
