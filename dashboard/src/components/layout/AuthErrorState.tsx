import { ShieldAlert } from 'lucide-react'

interface AuthErrorStateProps {
  heading?: string
  body?: string
}

export function AuthErrorState({
  heading = 'Authentication required',
  body = 'Add your API key in Settings to continue',
}: AuthErrorStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        minHeight: '300px',
        gap: '12px',
        padding: '32px',
        textAlign: 'center',
      }}
    >
      <ShieldAlert size={48} style={{ color: '#6366f1' }} />
      <h2 style={{ fontSize: '20px', fontWeight: 600, margin: 0 }}>{heading}</h2>
      <p style={{ color: '#71717a', fontSize: '14px', margin: 0 }}>{body}</p>
    </div>
  )
}
