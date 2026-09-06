import { useState } from 'react'
import { useSignIn, useSignUp } from '@clerk/clerk-react'
import { C, s } from '../ui/tokens.js'

export default function DriverLoginForm({ onSuccess, onSwitchToPassenger }) {
  const { isLoaded: isSignInLoaded, signIn, setActive: setSignInActive } = useSignIn()
  const { isLoaded: isSignUpLoaded, signUp, setActive: setSignUpActive } = useSignUp()

  const [mode, setMode] = useState('signin') // 'signin' | 'signup'
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [licensePlate, setLicensePlate] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  // ─── Driver Sign In (Strictly Credential-Based) ──────────────────────────────
  const handleDriverSignIn = async (e) => {
    e.preventDefault()
    if (!isSignInLoaded) return
    setErrorMsg('')
    setLoading(true)

    try {
      const result = await signIn.create({
        identifier: identifier.trim(),
        password: password,
      })

      if (result.status === 'complete') {
        await setSignInActive({ session: result.createdSessionId })
        onSuccess?.()
      } else {
        setErrorMsg('Additional authentication step required. Please check your email/SMS.')
      }
    } catch (err) {
      const msg = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Invalid driver credentials.'
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  // ─── Driver Sign Up & Vehicle Registration ──────────────────────────────────
  const handleDriverSignUp = async (e) => {
    e.preventDefault()
    if (!isSignUpLoaded) return
    setErrorMsg('')
    setLoading(true)

    try {
      const [firstName, ...rest] = name.trim().split(' ')
      const lastName = rest.join(' ') || ''

      const result = await signUp.create({
        emailAddress: identifier.trim(),
        password: password,
        firstName: firstName || 'Driver',
        lastName: lastName,
      })

      if (result.status === 'complete') {
        await setSignUpActive({ session: result.createdSessionId })
        onSuccess?.()
      } else if (result.status === 'missing_requirements') {
        // Prepare email verification if required by Clerk policy
        await signUp.prepareEmailAddressVerification({ strategy: 'email_code' })
        setErrorMsg('Verification code sent to your email. Please verify to complete driver onboarding.')
      }
    } catch (err) {
      const msg = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Registration failed.'
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s({ background: C.surface, border: `1px solid ${C.border2}`, borderRadius: 14, padding: 22, boxShadow: '0 12px 32px rgba(0,0,0,0.25)' })}>
      {/* Header Banner */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>🚗</span>
          <span style={s({ color: C.accent, fontSize: 13, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' })}>
            Driver & Fleet Portal
          </span>
        </div>
        <span style={s({ fontSize: 10, color: C.muted2, background: C.surface2, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999, fontWeight: 700 })}>
          CREDENTIALS ONLY
        </span>
      </div>

      {/* Strict Isolation Notice */}
      <div style={s({ background: 'rgba(234, 179, 8, 0.08)', border: '1px solid rgba(234, 179, 8, 0.25)', borderRadius: 9, padding: '9px 12px', marginBottom: 16 })}>
        <p style={s({ color: '#facc15', fontSize: 11, lineHeight: 1.4, margin: 0, display: 'flex', alignItems: 'center', gap: 6 })}>
          <span>🔒</span>
          <span><strong>Authentication Isolation:</strong> Social logins are restricted. Drivers must authenticate using verified company/fleet credentials.</span>
        </p>
      </div>

      {errorMsg && (
        <div style={s({ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 9, padding: '9px 12px', marginBottom: 14 })}>
          <p style={s({ color: '#f87171', fontSize: 11, margin: 0 })}>✕ {errorMsg}</p>
        </div>
      )}

      <form onSubmit={mode === 'signin' ? handleDriverSignIn : handleDriverSignUp}>
        {mode === 'signup' && (
          <div style={{ marginBottom: 12 }}>
            <label style={s({ display: 'block', color: C.muted, fontSize: 11, fontWeight: 700, marginBottom: 5 })}>Full Legal Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Rajesh Kumar"
              value={name}
              onChange={e => setName(e.target.value)}
              style={s({ width: '100%', padding: '10px 12px', background: C.surface2, border: `1px solid ${C.border2}`, color: C.text, borderRadius: 8, fontSize: 12, outline: 'none' })}
            />
          </div>
        )}

        <div style={{ marginBottom: 12 }}>
          <label style={s({ display: 'block', color: C.muted, fontSize: 11, fontWeight: 700, marginBottom: 5 })}>
            {mode === 'signin' ? 'Driver Email or Username' : 'Driver Email'}
          </label>
          <input
            type="text"
            required
            placeholder="driver@smartroute.ai"
            value={identifier}
            onChange={e => setIdentifier(e.target.value)}
            style={s({ width: '100%', padding: '10px 12px', background: C.surface2, border: `1px solid ${C.border2}`, color: C.text, borderRadius: 8, fontSize: 12, outline: 'none' })}
          />
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={s({ display: 'block', color: C.muted, fontSize: 11, fontWeight: 700, marginBottom: 5 })}>Password</label>
          <input
            type="password"
            required
            placeholder="••••••••••••"
            value={password}
            onChange={e => setPassword(e.target.value)}
            style={s({ width: '100%', padding: '10px 12px', background: C.surface2, border: `1px solid ${C.border2}`, color: C.text, borderRadius: 8, fontSize: 12, outline: 'none' })}
          />
        </div>

        {mode === 'signup' && (
          <div style={{ marginBottom: 14 }}>
            <label style={s({ display: 'block', color: C.muted, fontSize: 11, fontWeight: 700, marginBottom: 5 })}>Vehicle License Plate</label>
            <input
              type="text"
              required
              placeholder="KA-01-AB-1234"
              value={licensePlate}
              onChange={e => setLicensePlate(e.target.value.toUpperCase())}
              style={s({ width: '100%', padding: '10px 12px', background: C.surface2, border: `1px solid ${C.border2}`, color: C.text, borderRadius: 8, fontSize: 12, outline: 'none', letterSpacing: '0.05em' })}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={s({
            width: '100%',
            padding: '11px 14px',
            background: `linear-gradient(135deg, ${C.accent} 0%, #00a887 100%)`,
            color: C.bg,
            border: 'none',
            borderRadius: 9,
            fontSize: 12,
            fontWeight: 800,
            cursor: loading ? 'not-allowed' : 'pointer',
            boxShadow: '0 4px 14px rgba(0,201,167,0.35)',
            opacity: loading ? 0.7 : 1,
            transition: 'all 0.2s ease',
          })}
        >
          {loading ? 'Authenticating…' : mode === 'signin' ? 'Sign In to Driver Portal' : 'Register Driver Profile'}
        </button>
      </form>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
        <button
          type="button"
          onClick={() => setMode(m => m === 'signin' ? 'signup' : 'signin')}
          style={s({ background: 'none', border: 'none', color: C.muted2, fontSize: 11, cursor: 'pointer', textDecoration: 'underline' })}
        >
          {mode === 'signin' ? 'Apply as a new Driver' : 'Already a registered driver?'}
        </button>

        <button
          type="button"
          onClick={onSwitchToPassenger}
          style={s({ background: 'none', border: 'none', color: C.accent, fontSize: 11, fontWeight: 700, cursor: 'pointer' })}
        >
          ← Passenger Login
        </button>
      </div>
    </div>
  )
}
