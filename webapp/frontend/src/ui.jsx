import { Component } from 'react'

export function ErrorBanner({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="error-banner" role="alert">
      <strong>Something went wrong.</strong>
      <span>{error.message}</span>
      {onRetry && <button className="secondary" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Loading({ label = 'Loading…' }) {
  return <div className="empty-state">{label}</div>
}

/** Keeps one failed view from blanking the whole app. */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card">
          <ErrorBanner
            error={this.state.error}
            onRetry={() => this.setState({ error: null })}
          />
        </div>
      )
    }
    return this.props.children
  }
}
