import { useState } from 'react'
import { useSignIn, useSignUp } from '@clerk/clerk-react'
import { CarFront, Loader2, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'

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
        password,
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
        password,
        firstName: firstName || 'Driver',
        lastName,
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

        <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs">
          <button
            type="button"
            onClick={() => setMode((m) => (m === 'signin' ? 'signup' : 'signin'))}
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
