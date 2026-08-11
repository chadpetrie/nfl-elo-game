import { useState } from 'react'
import WeekView from './WeekView.jsx'
import SettingsView from './SettingsView.jsx'
import ScoreboardView from './ScoreboardView.jsx'
import RankingsView from './RankingsView.jsx'
import { ErrorBoundary } from './ui.jsx'

const TABS = [
  { id: 'week', label: 'This Week', view: WeekView },
  { id: 'scoreboard', label: 'Scoreboard', view: ScoreboardView },
  { id: 'rankings', label: 'Power Ratings', view: RankingsView },
  { id: 'settings', label: 'Settings', view: SettingsView },
]

export default function App() {
  const [tab, setTab] = useState('week')
  const Active = TABS.find((t) => t.id === tab).view

  return (
    <div className="app">
      <div className="app-header">
        <h1>NFL Predictions</h1>
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? 'active' : ''}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Remounting per tab keeps a crash in one view from poisoning the others. */}
      <ErrorBoundary key={tab}>
        <Active />
      </ErrorBoundary>
    </div>
  )
}
