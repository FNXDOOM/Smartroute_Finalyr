import { useState } from 'react'
import { useSignIn, useSignUp, useAuth } from '@clerk/clerk-react'
import { CarFront, Loader2, Lock, MailCheck } from 'lucide-react'
import { authApi } from '../services/api.js'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'

export default function DriverLoginForm({ onSuccess, onSwitchToPassenger }) {
  const { isLoaded: isSignInLoaded, signIn, setActive: setSignInActive } = useSignIn()
  const { isLoaded: isSignUpLoaded, signUp, setActive: setSignUpActive } = useSignUp()
  const { getToken } = useAuth()

  const [mode, setMode] = useState('signin') // 'signin' | 'signup'
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [licensePlate, setLicensePlate] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [noticeMsg, setNoticeMsg] = useState('')
  const [pendingVerification, setPendingVerification] = useState(false)
  const [code, setCode] = useState('')

  // ─── Wait for Clerk to hand out a usable session token ───────────────────────
  // Firing an authenticated call the instant after setActive races session
  // propagation and comes back 401. Poll briefly instead.
  const waitForSessionToken = async (tries = 6, delayMs = 800) => {
    for (let i = 0; i < tries; i += 1) {
      try {
        const token = await getToken()
        if (token) return token
      } catch { /* retry until attempts run out */ }
      await new Promise((r) => setTimeout(r, delayMs))
    }
    return null
  }

  // ─── Driver Sign In (Strictly Credential-Based) ──────────────────────────────
  const handleDriverSignIn = async (e) => {
    e.preventDefault()
    if (!isSignInLoaded) return
    setErrorMsg('')
    setNoticeMsg('')
    setLoading(true)

    try {
      const result = await signIn.create({
        identifier: identifier.trim(),
        password,
      })

      if (result.status === 'complete') {
        await setSignInActive({ session: result.createdSessionId })
        // Returning drivers already carry their role. Accounts that never
        // finished onboarding (still passenger) are routed to the in-app
        // driver application view — it must live inside the app because the
        // login screen unmounts the moment sign-in completes.
        try {
          await waitForSessionToken(3, 700)
          const profile = await authApi.getProfile()
          if (profile?.role === 'driver') {
            await onSuccess?.()
          } else {
            await onSuccess?.('driver-apply')
          }
        } catch {
          await onSuccess?.()
        }
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

  // ─── Promote the fresh Clerk account to driver + register the vehicle ────────
  // Backend auto-provisions every new user as passenger; this is the step
  // that flips role to driver / pending_verification (admin approval still
  // required before dispatch access).
  const submitDriverApplication = async () => {
    const plate = licensePlate.trim().toUpperCase()
    if (!plate) {
      setErrorMsg('Vehicle license plate is required to complete driver onboarding.')
      return false
    }
    const token = await waitForSessionToken()
    if (!token) {
      setErrorMsg('Session is still initializing. Please wait a moment and try again.')
      return false
    }
    try {
      await authApi.applyDriver({ license_plate: plate }, token)
      return true
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = (typeof detail === 'string' && detail)
        || err.errors?.[0]?.longMessage
        || err.errors?.[0]?.message
        || 'Driver application failed. Please check the license plate and try again.'
      setErrorMsg(msg)
      return false
    }
  }

  // ─── Driver Sign Up & Vehicle Registration ──────────────────────────────────
  const handleDriverSignUp = async (e) => {
    e.preventDefault()
    if (!isSignUpLoaded) return
    setErrorMsg('')
    setNoticeMsg('')
    setLoading(true)

    try {
      const [firstName, ...rest] = name.trim().split(' ')
      const lastName = rest.join(' ') || ''

      const result = await signUp.create({
        emailAddress: identifier.trim(),
        password,
        firstName: firstName || 'Driver',
        lastName,
      })

      if (result.status === 'complete') {
        await setSignUpActive({ session: result.createdSessionId })
        // Promote to driver (or surface the plate error); then refresh to
        // server truth via onSuccess.
        await submitDriverApplication()
        await onSuccess?.()
      } else if (result.status === 'missing_requirements') {
        // Prepare email verification if required by Clerk policy
        await signUp.prepareEmailAddressVerification({ strategy: 'email_code' })
        setPendingVerification(true)
        setNoticeMsg(`Verification code sent to ${identifier.trim()}. Enter it below to complete driver onboarding.`)
      }
    } catch (err) {
      const msg = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Registration failed.'
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  // ─── Verify emailed code to finish driver onboarding ─────────────────────────
  const handleVerifyCode = async (e) => {
    e.preventDefault()
    if (!isSignUpLoaded || !code.trim()) return
    setErrorMsg('')
    setLoading(true)

    try {
      const result = await signUp.attemptEmailAddressVerification({ code: code.trim() })
      if (result.status === 'complete') {
        await setSignUpActive({ session: result.createdSessionId })
        await submitDriverApplication()
        await onSuccess?.()
      } else {
        setErrorMsg('Verification incomplete. Please try again or request a new code.')
      }
    } catch (err) {
      const msg = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Invalid verification code.'
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleResendCode = async () => {
    if (!isSignUpLoaded) return
    setErrorMsg('')
    setLoading(true)

    try {
      await signUp.prepareEmailAddressVerification({ strategy: 'email_code' })
      setNoticeMsg(`A new verification code was sent to ${identifier.trim()}.`)
    } catch (err) {
      const msg = err.errors?.[0]?.longMessage || err.errors?.[0]?.message || 'Could not resend the code.'
      setErrorMsg(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleModeSwitch = () => {
    setMode((m) => (m === 'signin' ? 'signup' : 'signin'))
    setErrorMsg('')
    setNoticeMsg('')
    setPendingVerification(false)
    setCode('')
  }

  return (
    <Card className="shadow-lg">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-wide">
            <CarFront className="h-4 w-4 text-primary" /> Driver & Fleet Portal
          </CardTitle>
          <Badge variant="secondary">Credentials only</Badge>
        </div>
        <CardDescription className="flex items-center gap-1.5 pt-1 text-xs">
          <Lock className="h-3 w-3" /> Social logins are disabled here — fleet credentials only.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {errorMsg && (
          <p className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{errorMsg}</p>
        )}
        {noticeMsg && (
          <p className="mb-3 flex items-start gap-2 rounded-md border border-primary/30 bg-primary/[0.07] px-3 py-2 text-xs text-foreground">
            <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>{noticeMsg}</span>
          </p>
        )}

        {pendingVerification ? (
          <form onSubmit={handleVerifyCode} className="space-y-3.5">
            <div className="space-y-1.5">
              <Label htmlFor="driver-code">6-Digit Verification Code</Label>
              <Input
                id="driver-code"
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="••••••"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="text-center text-lg tracking-[0.5em]"
              />
            </div>

            <Button type="submit" className="w-full" disabled={loading || code.trim().length < 6}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? 'Verifying…' : 'Verify Email & Finish Onboarding'}
            </Button>

            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={handleResendCode}
                disabled={loading}
                className="text-muted-foreground underline hover:text-foreground disabled:opacity-50"
              >
                Resend code
              </button>
              <button
                type="button"
                onClick={handleModeSwitch}
                className="font-semibold text-primary hover:underline"
              >
                ← Back to registration
              </button>
            </div>
          </form>
        ) : (
        <form onSubmit={mode === 'signin' ? handleDriverSignIn : handleDriverSignUp} className="space-y-3.5">
          {mode === 'signup' && (
            <div className="space-y-1.5">
              <Label htmlFor="driver-name">Full Legal Name</Label>
              <Input id="driver-name" required placeholder="e.g. Rajesh Kumar" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="driver-id">{mode === 'signin' ? 'Driver Email or Username' : 'Driver Email'}</Label>
            <Input id="driver-id" required placeholder="driver@smartroute.ai" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="driver-pass">Password</Label>
            <Input id="driver-pass" type="password" required placeholder="••••••••••••" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>

          {mode === 'signup' && (
            <div className="space-y-1.5">
              <Label htmlFor="driver-plate">Vehicle License Plate</Label>
              <Input
                id="driver-plate"
                required
                placeholder="KA-01-AB-1234"
                value={licensePlate}
                onChange={(e) => setLicensePlate(e.target.value.toUpperCase())}
                className="uppercase tracking-widest"
              />
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? 'Authenticating…' : mode === 'signin' ? 'Sign In to Driver Portal' : 'Register Driver Profile'}
          </Button>
        </form>
        )}

        <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs">
          <button
            type="button"
            onClick={handleModeSwitch}
            className="text-muted-foreground underline hover:text-foreground"
          >
            {mode === 'signin' ? 'Apply as a new Driver' : 'Already a registered driver?'}
          </button>
          <button type="button" onClick={onSwitchToPassenger} className="font-semibold text-primary hover:underline">
            ← Passenger Login
          </button>
        </div>
      </CardContent>
    </Card>
  )
}
