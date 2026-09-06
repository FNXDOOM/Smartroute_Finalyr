import { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { CarFront, Loader2, ShieldCheck } from 'lucide-react'
import { authApi } from '../services/api.js'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// In-app driver onboarding bridge. Reached after driver-portal sign-in when
// the account is still a passenger (the login screen unmounts on sign-in, so
// the application step cannot live there). Also doubles as a plate-change
// form for active drivers. Admins are blocked: submitting would demote them.
export default function DriverApplyView({ user, setView, toast, onApplied }) {
  const { getToken } = useAuth()
  const [plate, setPlate] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const goHome = () => setView?.(user?.role === 'driver' ? 'driver-home' : user?.role === 'admin' ? 'admin-overview' : 'home')

  if (user?.role === 'admin') {
    return (
      <div className="mx-auto flex w-full max-w-[520px] flex-col items-center justify-center gap-4 p-6 text-center">
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="flex items-center justify-center gap-2 text-base">
              <ShieldCheck className="h-5 w-5 text-primary" /> Driver application unavailable
            </CardTitle>
            <CardDescription>Admin accounts cannot apply as drivers — doing so would remove admin access.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" className="w-full" onClick={goHome}>Back to dashboard</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const submit = async (e) => {
    e.preventDefault()
    const value = plate.trim().toUpperCase()
    if (!value) {
      setError('Vehicle license plate is required.')
      return
    }
    setError('')
    setLoading(true)
    try {
      // Attach our own token: deterministic regardless of interceptor state.
      const token = await getToken().catch(() => null)
      await authApi.applyDriver({ license_plate: value }, token || undefined)
      toast?.('success', 'Driver application submitted', 'An admin will review your application shortly.')
      await onApplied?.()
    } catch (err) {
      const detail = err.response?.data?.detail
      setError((typeof detail === 'string' && detail) || 'Application failed. Please check the plate and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[520px] flex-col items-center justify-center gap-4 p-6">
      <Card className="w-full shadow-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-wide">
            <CarFront className="h-4 w-4 text-primary" /> Become a driver
          </CardTitle>
          <CardDescription>
            Signed in as <strong className="text-foreground">{user?.email || 'your account'}</strong>.
            Submit your vehicle to request driver access — an admin approves every application.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
          )}
          <form onSubmit={submit} className="space-y-3.5">
            <div className="space-y-1.5">
              <Label htmlFor="apply-plate">Vehicle License Plate</Label>
              <Input
                id="apply-plate"
                required
                placeholder="KA-01-AB-1234"
                value={plate}
                onChange={(e) => setPlate(e.target.value.toUpperCase())}
                className="uppercase tracking-widest"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? 'Submitting…' : 'Submit driver application'}
            </Button>
            <Button type="button" variant="ghost" className="w-full" onClick={goHome}>
              ← Back to dashboard
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
