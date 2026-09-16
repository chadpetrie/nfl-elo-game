import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { ErrorBanner, Loading } from './ui.jsx'

const DEFAULTS = { hfa: 32.0, k: 20.0, revert: 1 / 3, mov_base: 2.2, blend_weight: 0.5 }

const FIELDS = [
  { key: 'hfa', label: 'Home field advantage', hint: 'Elo points added to the home team before forecasting (recalibrated from 2021-2025 results; 538 originally used 65)', min: 0, max: 200, step: 1 },
  { key: 'k', label: 'K-factor', hint: 'How fast ratings move after each game (538 default: 20)', min: 1, max: 60, step: 1 },
  { key: 'revert', label: 'Season reversion', hint: 'Share of each rating pulled back toward the mean between seasons (538 default: 0.33)', min: 0, max: 1, step: 0.01 },
  { key: 'mov_base', label: 'Margin-of-victory base', hint: 'Base of the blowout multiplier applied to K (538 default: 2.2)', min: 0.5, max: 5, step: 0.1 },
  { key: 'blend_weight', label: 'Elo weight in Combined', hint: '1.0 = Combined is pure Elo, 0.0 = Combined is pure Vegas', min: 0, max: 1, step: 0.05 },
]

const isDirty = (a, b) => FIELDS.some((f) => Math.abs(a[f.key] - b[f.key]) > 1e-9)

export default function SettingsView() {
  const [params, setParams] = useState(null)
  const [saved, setSaved] = useState(null)
  const [status, setStatus] = useState('')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api.getParams()
      .then((p) => { setParams(p); setSaved(p) })
      .catch(setError)
  }, [])

  useEffect(load, [load])

  if (error && !params) return <div className="card"><ErrorBanner error={error} onRetry={load} /></div>
  if (!params) return <div className="card"><Loading /></div>

  const update = (key, value) => setParams((p) => ({ ...p, [key]: value }))

  const save = async () => {
    setSaving(true)
    setStatus('Replaying every game since 1920…')
    setError(null)
    try {
      const next = await api.saveParams(params)
      setParams(next)
      setSaved(next)
      setStatus('Saved — predictions recomputed')
      setTimeout(() => setStatus(''), 2500)
    } catch (e) {
      setError(e)
      setStatus('')
    } finally {
      setSaving(false)
    }
  }

  const dirty = saved && isDirty(params, saved)

  return (
    <div className="card">
      <p className="muted">
        These parameters drive the Elo model used for the "Elo" and "Combined" predictions
        everywhere in this app. Changing them replays every game since 1920, so it can take
        a moment after saving.
      </p>
      <ErrorBanner error={error} onRetry={() => setError(null)} />
      <div className="params-form">
        {FIELDS.map((f) => (
          <div className="param-field" key={f.key}>
            <label htmlFor={`param-${f.key}`}>
              {f.label} — <span className="param-value">{Number(params[f.key]).toFixed(2)}</span>
            </label>
            <input
              id={`param-${f.key}`}
              type="range"
              min={f.min}
              max={f.max}
              step={f.step}
              value={params[f.key]}
              onChange={(e) => update(f.key, Number(e.target.value))}
            />
            <span className="hint">{f.hint}</span>
          </div>
        ))}
      </div>
      <button className="primary" onClick={save} disabled={saving || !dirty}>
        {saving ? 'Recomputing…' : 'Save & Recompute'}
      </button>
      <button
        className="secondary"
        style={{ marginLeft: 10 }}
        disabled={saving}
        onClick={() => setParams({ ...params, ...DEFAULTS })}
      >
        Reset to defaults
      </button>
      {dirty && !saving && <span className="status-msg warn">Unsaved changes</span>}
      {status && <span className="status-msg">{status}</span>}
    </div>
  )
}
