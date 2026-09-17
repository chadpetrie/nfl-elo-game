import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner, Loading } from './ui.jsx'
import TotalsCard from './TotalsCard.jsx'

const SOURCES = [
  { id: 'elo', label: 'Elo', className: 'col-elo' },
  { id: 'vegas', label: 'Vegas', className: 'col-vegas' },
  { id: 'combined', label: 'Combined', className: 'col-combined' },
]

function pct(prob) {
  return prob == null ? null : Math.round(prob * 100)
}

function actualWinner(g) {
  if (g.result1 === 1) return g.team1
  if (g.result1 === 0) return g.team2
  return null
}

// Broadcast-window tint. date is parsed as a UTC calendar date (not local midnight) so the
// weekday can't shift with the viewer's timezone; gametime is already ET, the convention every
// NFL broadcast window ("the early games", "Sunday night") is anchored to regardless of viewer.
function timeSlot(g) {
  const [y, m, d] = g.date.split('-').map(Number)
  const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay() // 0 = Sun, 1 = Mon, 4 = Thu
  if (weekday === 4) return 'slot-thu'
  if (weekday === 1) return 'slot-mon'
  if (weekday === 0) {
    const hour = g.gametime ? Number(g.gametime.split(':')[0]) : NaN
    // 4:00 PM ET is the standard split between the early and late Sunday windows; Sunday Night
    // Football (8:20 PM) counts as "late" too rather than a 5th color.
    if (!Number.isNaN(hour) && hour >= 16) return 'slot-sun-late'
  }
  return null // Sunday early, Saturday, or an unscheduled kickoff time: no highlight
}

// The mobile card layout needs each cell's column name in the DOM (not just CSS ::before
// content, which screen readers don't reliably expose) - hidden on the desktop table, where the
// real <th> headers already do that job.
function CellLabel({ text }) {
  return <span className="cell-label">{text}</span>
}

function PredictionCell({ game, source, maxRank }) {
  const prob = game[`${source.id}_prob`]
  const pick = game[`${source.id}_pick`]
  const rank = game[`${source.id}_rank`]
  if (prob == null) {
    return (
      <td className={source.className}>
        <CellLabel text={source.label} />
        <span className="na">odds not posted</span>
      </td>
    )
  }
  const winner = actualWinner(game)
  const correct = winner != null ? pick === winner : null

  return (
    <td className={source.className}>
      <CellLabel text={source.label} />
      <div className="pred">
        <span className={`rank-badge ${rank === maxRank ? 'top' : ''}`}>{rank}</span>
        <span className="pred-team">{pick}</span>
        <span className="pred-pct">{pct(prob)}%</span>
        {correct === true && <span className="result-correct">✓</span>}
        {correct === false && <span className="result-wrong">✗</span>}
      </div>
    </td>
  )
}

function PickCell({ game, maxConfidence, duplicate, onSave, onConfidenceChange, onClear }) {
  const pick = game.user_pick
  const team = pick?.team ?? ''
  const confidence = pick?.confidence ?? ''
  const winner = actualWinner(game)
  const correct = team && winner != null ? team === winner : null

  const changeTeam = (value) => {
    if (!value) return onClear(game.game_id)
    // A pick needs some confidence attached or it scores nothing; seed it from the model.
    onSave(game.game_id, value, confidence === '' ? game.combined_rank ?? null : Number(confidence))
  }

  const changeConfidence = (value) => {
    if (!team) return
    if (value === '') return onSave(game.game_id, team, null)
    onConfidenceChange(game.game_id, team, Number(value))
  }

  return (
    <td>
      <CellLabel text="Your pick" />
      <div className="pick-cell">
        <select value={team} onChange={(e) => changeTeam(e.target.value)} aria-label="Your pick">
          <option value="">—</option>
          <option value={game.team1}>{game.team1}</option>
          <option value={game.team2}>{game.team2}</option>
        </select>
        <select
          className={duplicate ? 'dupe' : ''}
          value={confidence}
          disabled={!team}
          title={duplicate ? 'This confidence value is used more than once this week' : ''}
          onChange={(e) => changeConfidence(e.target.value)}
          aria-label="Confidence"
        >
          <option value="">—</option>
          {Array.from({ length: maxConfidence }, (_, i) => maxConfidence - i).map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        {correct === true && <span className="result-correct">✓</span>}
        {correct === false && <span className="result-wrong">✗</span>}
      </div>
    </td>
  )
}

// Confidence is a 1..N permutation, not just a label. Reassigning one game's confidence moves it
// into another game's slot; everything strictly between the old and new position shifts by one
// to close the gap it left and open the gap it needs, so the whole week stays a clean permutation
// with nothing duplicated or skipped - the same mechanics as moving an item within a ranked list.
function shiftedConfidences(games, gameId, newConfidence) {
  const target = games.find((g) => g.game_id === gameId)
  const oldConfidence = target?.user_pick?.confidence ?? null
  const updates = new Map([[gameId, newConfidence]])

  if (oldConfidence == null || newConfidence === oldConfidence) return updates

  for (const g of games) {
    if (g.game_id === gameId) continue
    const c = g.user_pick?.confidence
    if (c == null) continue
    if (newConfidence < oldConfidence && c >= newConfidence && c < oldConfidence) {
      updates.set(g.game_id, c + 1)
    } else if (newConfidence > oldConfidence && c > oldConfidence && c <= newConfidence) {
      updates.set(g.game_id, c - 1)
    }
  }
  return updates
}

function RecordChip({ label, stats, className }) {
  if (!stats || !stats.graded) return null
  return (
    <span className={`record-chip ${className || ''}`}>
      <strong>{label}</strong> {stats.correct}-{stats.graded - stats.correct}
      <span className="record-pool">{stats.earned}/{stats.possible} pts</span>
    </span>
  )
}

export default function WeekView() {
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState(null)
  const [weeks, setWeeks] = useState([])
  const [week, setWeek] = useState(null)
  const [games, setGames] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Season and week changes can be clicked faster than the API answers; only the newest
  // request for each is allowed to write to state.
  const weekReq = useRef(0)
  const gamesReq = useRef(0)

  const loadSeasons = useCallback(() => {
    setError(null)
    api.seasons()
      .then((s) => {
        setSeasons(s)
        setSeason((current) => (current == null && s.length ? s[0] : current))
        if (!s.length) setLoading(false)
      })
      .catch((e) => { setError(e); setLoading(false) })
  }, [])

  useEffect(loadSeasons, [loadSeasons])

  useEffect(() => {
    if (season == null) return
    const id = ++weekReq.current
    setError(null)
    api.weeks(season)
      .then((w) => {
        if (id !== weekReq.current) return
        setWeeks(w)
        setWeek(w.length ? (w.find((x) => x.current) ?? w[0]).week : null)
        if (!w.length) { setGames([]); setSummary(null); setLoading(false) }
      })
      .catch((e) => { if (id === weekReq.current) { setError(e); setLoading(false) } })
  }, [season])

  const loadGames = useCallback(() => {
    if (season == null || week == null) return
    const id = ++gamesReq.current
    setLoading(true)
    setError(null)
    api.games(season, week)
      .then((data) => {
        if (id !== gamesReq.current) return
        setGames(data.games)
        setSummary(data.summary)
        setLoading(false)
      })
      .catch((e) => {
        if (id !== gamesReq.current) return
        setError(e)
        setGames([])
        setSummary(null)
        setLoading(false)
      })
  }, [season, week])

  useEffect(loadGames, [loadGames])

  const applyPick = (gameId, user_pick) =>
    setGames((prev) => prev.map((g) => (g.game_id === gameId ? { ...g, user_pick } : g)))

  const savePick = async (gameId, team, confidence) => {
    const previous = games.find((g) => g.game_id === gameId)?.user_pick ?? null
    applyPick(gameId, { team, confidence })
    try {
      await api.savePick(gameId, team, confidence)
    } catch (e) {
      applyPick(gameId, previous)  // put the row back the way the server still sees it
      setError(e)
    }
  }

  const changeConfidenceWithShift = async (gameId, team, newConfidence) => {
    const shifted = shiftedConfidences(games, gameId, newConfidence)
    const payload = [...shifted.entries()].map(([id, confidence]) => ({
      id,
      team: id === gameId ? team : games.find((g) => g.game_id === id).user_pick.team,
      confidence,
    }))
    const previous = new Map(payload.map((p) => [p.id, games.find((g) => g.game_id === p.id)?.user_pick ?? null]))

    setGames((prev) => prev.map((g) => {
      const p = payload.find((x) => x.id === g.game_id)
      return p ? { ...g, user_pick: { team: p.team, confidence: p.confidence } } : g
    }))

    try {
      await Promise.all(payload.map((p) => api.savePick(p.id, p.team, p.confidence)))
    } catch (e) {
      setGames((prev) => prev.map((g) => (previous.has(g.game_id) ? { ...g, user_pick: previous.get(g.game_id) } : g)))
      setError(e)
    }
  }

  const clearPick = async (gameId) => {
    const previous = games.find((g) => g.game_id === gameId)?.user_pick ?? null
    applyPick(gameId, null)
    try {
      await api.clearPick(gameId)
    } catch (e) {
      applyPick(gameId, previous)
      setError(e)
    }
  }

  const autofill = async (sourceId) => {
    setBusy(true)
    setError(null)
    try {
      const targets = games
        .filter((g) => g[`${sourceId}_pick`] != null && g[`${sourceId}_rank`] != null)
        .map((g) => ({ id: g.game_id, team: g[`${sourceId}_pick`], confidence: g[`${sourceId}_rank`] }))
      for (const t of targets) {
        await api.savePick(t.id, t.team, t.confidence)
      }
      loadGames()
    } catch (e) {
      setError(e)
      loadGames()
    } finally {
      setBusy(false)
    }
  }

  const clearWeek = async () => {
    setBusy(true)
    setError(null)
    try {
      for (const g of games.filter((g) => g.user_pick)) {
        await api.clearPick(g.game_id)
      }
      loadGames()
    } catch (e) {
      setError(e)
      loadGames()
    } finally {
      setBusy(false)
    }
  }

  const maxRankFor = (id) =>
    games.reduce((m, g) => (g[`${id}_rank`] != null && g[`${id}_rank`] > m ? g[`${id}_rank`] : m), 0)

  const confidenceCounts = games.reduce((acc, g) => {
    const c = g.user_pick?.confidence
    if (c != null) acc[c] = (acc[c] || 0) + 1
    return acc
  }, {})
  const duplicates = Object.entries(confidenceCounts).filter(([, n]) => n > 1).map(([c]) => c)

  const weekLabel = weeks.find((w) => w.week === week)?.label ?? ''

  // As confidence gets assigned, the slate reorders live to show your ranking 16 down to 1 -
  // games you haven't ranked yet trail below it, in their original kickoff order (sort is
  // stable, so ties - including "both unranked" - keep the order they arrived in).
  const sortedGames = [...games].sort((a, b) => {
    const ca = a.user_pick?.confidence
    const cb = b.user_pick?.confidence
    if (ca != null && cb != null) return cb - ca
    if (ca != null) return -1
    if (cb != null) return 1
    return 0
  })

  return (
    <div>
      <div className="card">
        <div className="selectors">
          <div>
            <label htmlFor="season-select">Season</label>
            <select id="season-select" value={season ?? ''} onChange={(e) => setSeason(Number(e.target.value))}>
              {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="week-select">Week</label>
            <select id="week-select" value={week ?? ''} onChange={(e) => setWeek(Number(e.target.value))}>
              {weeks.map((w) => <option key={w.week} value={w.week}>{w.label}</option>)}
            </select>
          </div>
          <div className="autofill">
            <label>Fill my picks from</label>
            <div className="autofill-buttons">
              {SOURCES.map((s) => (
                <button key={s.id} className="secondary" disabled={busy || !games.length} onClick={() => autofill(s.id)}>
                  {s.label}
                </button>
              ))}
              <button className="secondary" disabled={busy || !games.some((g) => g.user_pick)} onClick={clearWeek}>
                Clear
              </button>
            </div>
          </div>
        </div>
        <div className="legend">
          {SOURCES.map((s) => (
            <span key={s.id}>
              <span className="swatch" style={{ background: `var(--accent-${s.id})` }} />{s.label}
            </span>
          ))}
          <span>Rank = confidence order within this week; higher means more confident.</span>
        </div>
        <div className="legend">
          <span><span className="swatch swatch-outline" style={{ background: 'var(--slot-thu-bg)' }} />Thursday night</span>
          <span><span className="swatch swatch-outline" style={{ background: 'var(--slot-sun-late-bg)' }} />Sunday late/night</span>
          <span><span className="swatch swatch-outline" style={{ background: 'var(--slot-mon-bg)' }} />Monday night</span>
        </div>
      </div>

      <ErrorBanner error={error} onRetry={error && !games.length ? loadSeasons : () => setError(null)} />

      {summary && summary.played > 0 && (
        <div className="card record-bar">
          <span className="record-title">{weekLabel} results</span>
          <RecordChip label="Elo" stats={summary.elo} className="col-elo" />
          <RecordChip label="Vegas" stats={summary.vegas} className="col-vegas" />
          <RecordChip label="Combined" stats={summary.combined} className="col-combined" />
          <RecordChip label="You" stats={summary.user} />
          {summary.played < summary.total && (
            <span className="muted">{summary.total - summary.played} game(s) not yet final</span>
          )}
        </div>
      )}

      {duplicates.length > 0 && (
        <div className="card warn-banner">
          Confidence {duplicates.join(', ')} used more than once. A confidence pool normally wants each
          number used exactly once per week.
        </div>
      )}

      <div className="card">
        {loading ? (
          <Loading />
        ) : games.length === 0 ? (
          <div className="empty-state">No games found for this week.</div>
        ) : (
          <div className="table-scroll">
            <table className="week-table">
              <thead>
                <tr>
                  <th>Matchup</th>
                  <th>Kickoff</th>
                  <th>Result</th>
                  {SOURCES.map((s) => <th key={s.id} className={s.className}>{s.label}</th>)}
                  <th>Your pick</th>
                </tr>
              </thead>
              <tbody>
                {sortedGames.map((g) => (
                  <tr
                    key={g.game_id}
                    className={[g.result1 != null ? 'played' : '', timeSlot(g)].filter(Boolean).join(' ')}
                  >
                    <td className="matchup">
                      <CellLabel text="Matchup" />
                      <span className="matchup-value">
                        <span className="away">{g.team2}</span> @ {g.team1}
                      </span>
                    </td>
                    <td className="kickoff">
                      <CellLabel text="Kickoff" />
                      {g.date}{g.gametime ? ` ${g.gametime}` : ''}
                    </td>
                    <td>
                      <CellLabel text="Result" />
                      {g.result1 != null ? (
                        <span className="final-score">{g.team2} {g.score2} - {g.score1} {g.team1}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    {SOURCES.map((s) => (
                      <PredictionCell key={s.id} game={g} source={s} maxRank={maxRankFor(s.id)} />
                    ))}
                    <PickCell
                      game={g}
                      maxConfidence={games.length}
                      duplicate={g.user_pick?.confidence != null && confidenceCounts[g.user_pick.confidence] > 1}
                      onSave={savePick}
                      onConfidenceChange={changeConfidenceWithShift}
                      onClear={clearPick}
                    />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <TotalsCard season={season} week={week} />
    </div>
  )
}
