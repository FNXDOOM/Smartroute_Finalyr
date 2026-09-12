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
    <div className="flex min-h-screen items-center justify-center bg-white p-6 dark:bg-black">
      <Card className="w-full max-w-[480px] rounded-2xl text-center shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
        <CardHeader className="pt-8">
          <span className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-xl bg-black text-white dark:bg-white dark:text-black">
            <Hourglass className="h-7 w-7" />
          </span>
          <CardTitle className="text-[24px] font-bold tracking-[-0.02em]">Verification in progress</CardTitle>
          <CardDescription className="mt-2 text-[14px]">
            Welcome, <strong className="text-black dark:text-white">{user?.name || 'Partner'}</strong>. Your driver profile is under review.
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
              <Badge variant="secondary">Pending verification</Badge>
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
              <li>License plate and vehicle allocation under review.</li>
              <li>City transit route permissions pending clearance.</li>
              <li>Safety credential check in progress.</li>
            </ul>
          </div>

          <div className="flex flex-col gap-2">
            <Button onClick={handleCheckStatus} disabled={checking} className="h-12">
              {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {checking ? 'Checking status…' : 'Check approval status'}
            </Button>
            <Button variant="outline" onClick={onLogout} className="h-12">Sign out</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
