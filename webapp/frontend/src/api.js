const BASE = '/api'

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
  }
}

async function request(path, options) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    // fetch only rejects when the request never completed - the server is down or restarting.
    throw new ApiError(0, 'Could not reach the server. Is start_app.bat still running?')
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // non-JSON error body; the status line is the best message available
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  seasons: () => request('/seasons'),
  weeks: (season) => request(`/weeks?season=${season}`),
  games: (season, week) => request(`/games?season=${season}&week=${week}`),
  savePick: (gameId, team, confidence) =>
    request(`/games/${encodeURIComponent(gameId)}/pick`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team, confidence }),
    }),
  clearPick: (gameId) =>
    request(`/games/${encodeURIComponent(gameId)}/pick`, { method: 'DELETE' }),
  getParams: () => request('/params'),
  saveParams: (params) =>
    request('/params', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),
  rankings: (season) => request(season ? `/rankings?season=${season}` : '/rankings'),
  scoreboard: () => request('/scoreboard'),
}
