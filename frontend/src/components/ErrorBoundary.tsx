import { Component, ErrorInfo, ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[GridMint ErrorBoundary]', error, info)
  }

  handleReconnect = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{
        minHeight: '100vh', background: '#030c18', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        fontFamily: "'Inter',ui-sans-serif,system-ui",
      }}>
        <div style={{
          background: 'rgba(248,113,113,0.05)',
          border: '1px solid rgba(248,113,113,0.25)',
          borderRadius: 16, padding: '36px 40px', maxWidth: 480, textAlign: 'center',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚡</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#f87171', marginBottom: 8 }}>
            GridMint — Render Error
          </div>
          <div style={{ fontSize: 12, color: '#4e6272', lineHeight: 1.6, marginBottom: 20 }}>
            {this.state.error?.message ?? 'An unexpected error occurred in the dashboard.'}
          </div>
          <button
            onClick={this.handleReconnect}
            style={{
              padding: '10px 24px', borderRadius: 9,
              background: 'linear-gradient(90deg,#22d3ee,#a855f7)',
              color: '#020e18', fontWeight: 700, fontSize: 13, border: 'none', cursor: 'pointer',
            }}
          >
            🔄 Reconnect Dashboard
          </button>
        </div>
      </div>
    )
  }
}
