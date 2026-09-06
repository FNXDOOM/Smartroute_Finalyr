import { useState } from 'react'
import { C, s } from '../ui/tokens.js'
import { authApi } from '../services/api.js'

export default function DriverVerificationGate({ user, onRefreshProfile, onLogout, toast }) {
  const [checking, setChecking] = useState(false)

  const handleCheckStatus = async () => {
    setChecking(true)
    try {
      const profile = await authApi.getProfile()
      if (profile.driver_status === 'active') {
        toast('success', 'Driver Account Approved!', 'You now have full access to live routes and dispatch.')
        onRefreshProfile?.(profile)
      } else {
        toast('info', 'Verification in Progress', 'Your documents and vehicle license are still under review.')
      }
    } catch {
      toast('error', 'Unable to check status', 'Please check your connection and try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div style={s({ minHeight: '100vh', background: C.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 })}>
      <div style={s({ width: '100%', maxWidth: 480, background: C.surface, border: `1.5px solid ${C.border2}`, borderRadius: 16, padding: 28, boxShadow: '0 20px 48px rgba(0,0,0,0.3)', textAlign: 'center' })}>
        
        {/* Status Icon & Header */}
        <div style={s({ width: 64, height: 64, borderRadius: '50%', background: 'rgba(234, 179, 8, 0.12)', border: '2px solid rgba(234, 179, 8, 0.4)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, marginBottom: 16 })}>
          ⏳
        </div>

        <h2 style={s({ fontFamily: 'Bricolage Grotesque, sans-serif', color: C.text, fontSize: 20, fontWeight: 800, marginBottom: 6 })}>
          Driver Verification Required
        </h2>

        <p style={s({ color: C.muted2, fontSize: 13, lineHeight: 1.5, marginBottom: 20 })}>
          Welcome, <strong style={{ color: C.text }}>{user?.name || 'Partner'}</strong>! Your driver profile has been created and is currently awaiting dispatch verification.
        </p>

        {/* Verification Status Details Card */}
        <div style={s({ background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 12, padding: '16px 18px', textAlign: 'left', marginBottom: 22 })}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={s({ color: C.muted, fontSize: 11, fontWeight: 700, textTransform: 'uppercase' })}>Account Role</span>
            <span style={s({ color: C.accent, fontSize: 12, fontWeight: 800 })}>Driver / Fleet Partner</span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={s({ color: C.muted, fontSize: 11, fontWeight: 700, textTransform: 'uppercase' })}>Approval Status</span>
            <span style={s({ color: '#facc15', background: 'rgba(234, 179, 8, 0.15)', padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 800 })}>
              Pending Verification
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={s({ color: C.muted, fontSize: 11, fontWeight: 700, textTransform: 'uppercase' })}>Email Verified</span>
            <span style={s({ color: C.text, fontSize: 12, fontWeight: 600 })}>{user?.email || 'N/A'}</span>
          </div>
        </div>

        {/* Security / Requirements checklist */}
        <div style={s({ background: 'rgba(0, 201, 167, 0.06)', border: `1px solid ${C.accent}33`, borderRadius: 10, padding: '12px 14px', textAlign: 'left', marginBottom: 24 })}>
          <p style={s({ color: C.accent, fontSize: 11, fontWeight: 800, textTransform: 'uppercase', marginBottom: 6, letterSpacing: '0.04em' })}>
            Verification Checklist
          </p>
          <p style={s({ color: C.muted2, fontSize: 11, lineHeight: 1.5, margin: 0 })}>
            • License plate and vehicle allocation under review.<br />
            • City transit route permissions pending clearance.<br />
            • Background safety credential check in progress.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button
            type="button"
            onClick={handleCheckStatus}
            disabled={checking}
            style={s({
              width: '100%',
              padding: '12px 16px',
              background: `linear-gradient(135deg, ${C.accent} 0%, #00a887 100%)`,
              color: C.bg,
              border: 'none',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 800,
              cursor: checking ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(0,201,167,0.3)',
              opacity: checking ? 0.7 : 1,
            })}
          >
            {checking ? 'Checking Status…' : 'Check Approval Status ↻'}
          </button>

          <button
            type="button"
            onClick={onLogout}
            style={s({
              width: '100%',
              padding: '10px 16px',
              background: C.surface2,
              border: `1px solid ${C.border2}`,
              color: C.muted,
              borderRadius: 10,
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
            })}
          >
            Sign Out
          </button>
        </div>

      </div>
    </div>
  )
}
