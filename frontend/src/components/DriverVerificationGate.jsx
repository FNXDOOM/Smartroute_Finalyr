import { useState } from 'react'
import { Hourglass, Loader2, RefreshCw, ShieldAlert } from 'lucide-react'
import { authApi } from '../services/api.js'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

// The backend refuses every driver-capable endpoint unless driver_status is "active", so this screen stands in for all of them.
const STATUS_COPY = {
  pending_verification: {
    Icon: Hourglass,
    title: 'Verification in progress',
    intro: 'Your driver profile is under review.',
    badge: 'Pending verification',
    nextSteps: [
      'License plate and vehicle allocation under review.',
      'City transit route permissions pending clearance.',
      'Safety credential check in progress.',
    ],
    checkTitle: 'Verification in Progress',
    checkBody: 'Your documents and vehicle license are still under review.',
    actionLabel: 'Check approval status',
  },
  suspended: {
    Icon: ShieldAlert,
    title: 'Driver account suspended',
    intro: 'An administrator placed your driver account on hold.',
    badge: 'Suspended',
    nextSteps: [
      'Routes, carpool runs and fleet data are unavailable while suspended.',
      'An administrator must reinstate the account.',
      'Reinstatement takes effect the next time you check status.',
    ],
    checkTitle: 'Still Suspended',
    checkBody: 'An administrator needs to reinstate your driver account.',
    actionLabel: 'Check account status',
  },
}
const DEFAULT_COPY = STATUS_COPY.pending_verification

export default function DriverVerificationGate({ user, onRefreshProfile, onLogout, toast }) {
  const [checking, setChecking] = useState(false)
  const copy = STATUS_COPY[user?.driver_status] || DEFAULT_COPY
  const GateIcon = copy.Icon

  const handleCheckStatus = async () => {
    setChecking(true)
    try {
      const profile = await authApi.getProfile()
      if (profile.driver_status === 'active') {
        toast('success', 'Driver Account Approved!', 'You now have full access to live routes and dispatch.')
        onRefreshProfile?.(profile)
      } else {
        const nextCopy = STATUS_COPY[profile.driver_status] || DEFAULT_COPY
        toast('info', nextCopy.checkTitle, nextCopy.checkBody)
      }
    } catch {
      toast('error', 'Unable to check status', 'Please check your connection and try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-6 dark:bg-black">
      <Card className="w-full max-w-[480px] rounded-2xl text-center shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
        <CardHeader className="pt-8">
          <span className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-xl bg-black text-white dark:bg-white dark:text-black">
            <GateIcon className="h-7 w-7" />
          </span>
          <CardTitle className="text-[24px] font-bold tracking-[-0.02em]">{copy.title}</CardTitle>
          <CardDescription className="mt-2 text-[14px]">
            Welcome, <strong className="text-black dark:text-white">{user?.name || 'Partner'}</strong>. {copy.intro}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 p-6 text-left md:p-8 md:pt-4">
          <div className="space-y-3 rounded-xl border border-[#E2E2E2] p-5 text-sm dark:border-[#333333]">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8A8A8A]">Account role</span>
              <span className="text-[13px] font-semibold">Driver</span>
            </div>
            <Separator className="bg-[#E2E2E2] dark:bg-[#333333]" />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8A8A8A]">Status</span>
              <Badge variant="secondary">{copy.badge}</Badge>
            </div>
            <Separator className="bg-[#E2E2E2] dark:bg-[#333333]" />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8A8A8A]">Email</span>
              <span className="max-w-[220px] truncate text-[13px] font-medium">{user?.email || 'N/A'}</span>
            </div>
          </div>

          <div className="rounded-xl border border-[#E2E2E2] bg-[#F6F6F6] p-4 dark:border-[#333333] dark:bg-[#2A2A2A]">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[#545454] dark:text-[#AFAFAF]">What happens next</p>
            <ul className="list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-[#545454] dark:text-[#AFAFAF]">
              {copy.nextSteps.map((step) => <li key={step}>{step}</li>)}
            </ul>
          </div>

          <div className="flex flex-col gap-2">
            <Button onClick={handleCheckStatus} disabled={checking} className="h-12">
              {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {checking ? 'Checking status…' : copy.actionLabel}
            </Button>
            <Button variant="outline" onClick={onLogout} className="h-12">Sign out</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
