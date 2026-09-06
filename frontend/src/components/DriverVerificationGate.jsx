import { useState } from 'react'
import { Hourglass, Loader2, RefreshCw } from 'lucide-react'
import { authApi } from '../services/api.js'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

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
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-[480px] text-center shadow-xl">
        <CardHeader>
          <span className="mx-auto mb-2 flex h-16 w-16 items-center justify-center rounded-full border-2 border-amber-400/40 bg-amber-400/10">
            <Hourglass className="h-7 w-7 text-amber-500" />
          </span>
          <CardTitle className="font-display text-xl">Driver Verification Required</CardTitle>
          <CardDescription>
            Welcome, <strong className="text-foreground">{user?.name || 'Partner'}</strong>! Your driver profile is awaiting dispatch verification.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-left">
          <div className="space-y-2.5 rounded-lg border p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase text-muted-foreground">Account Role</span>
              <span className="text-xs font-extrabold">Driver / Fleet Partner</span>
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase text-muted-foreground">Approval Status</span>
              <Badge variant="secondary" className="border-amber-400/30 bg-amber-400/10 text-amber-600 dark:text-amber-400">Pending Verification</Badge>
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase text-muted-foreground">Email Verified</span>
              <span className="text-xs font-semibold">{user?.email || 'N/A'}</span>
            </div>
          </div>

          <div className="rounded-lg border border-primary/25 bg-primary/[0.05] p-3.5">
            <p className="mb-1.5 text-[11px] font-extrabold uppercase tracking-wider text-primary">Verification Checklist</p>
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>License plate and vehicle allocation under review.</li>
              <li>City transit route permissions pending clearance.</li>
              <li>Background safety credential check in progress.</li>
            </ul>
          </div>

          <div className="flex flex-col gap-2">
            <Button onClick={handleCheckStatus} disabled={checking}>
              {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {checking ? 'Checking Status…' : 'Check Approval Status'}
            </Button>
            <Button variant="outline" onClick={onLogout}>Sign Out</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
