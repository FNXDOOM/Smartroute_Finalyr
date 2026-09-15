/**
 * RazorpayPayment — reusable "Pay" button + checkout flow.
 *
 * States: idle → creating (backend create-order) → paying (checkout open) →
 * verifying (backend /payments/verify) → paid | failed | cancelled.
 *
 * SECURITY: success is shown ONLY after the backend verifies the payment
 * signature server-side (/payments/verify returns verified=true). Razorpay
 * Checkout returning control to the frontend is NOT treated as success.
 */
import { useEffect, useState } from 'react'
import { CheckCircle2, CreditCard, Loader2, TriangleAlert } from 'lucide-react'
import { paymentsApi } from '../services/api.js'
import { openRazorpayCheckout } from '../services/razorpay.js'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function RazorpayPayment({
  rideRequest,
  rideOptionId,
  rideOptionName,
  onPaid,
  className = '',
  disabled = false,
}) {
  const [phase, setPhase] = useState('idle') // idle|creating|paying|verifying|paid|failed
  const [error, setError] = useState('')

  // Cancelled checkout resets to idle so the user can retry cleanly.
  useEffect(() => {
    if (phase !== 'cancelled') return
    const timer = setTimeout(() => setPhase('idle'), 2500)
    return () => clearTimeout(timer)
  }, [phase])

  const handlePay = async () => {
    setError('')
    setPhase('creating')
    let checkoutData
    try {
      checkoutData = await paymentsApi.createOrder({
        ride_request_id: rideRequest?.id ?? null,
        ride_option_id: rideOptionId,
      })
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not start the payment. Please try again.')
      setPhase('failed')
      return
    }

    setPhase('paying')
    const result = await openRazorpayCheckout(
      {
        razorpay_key_id: checkoutData.razorpay_key_id,
        razorpay_order_id: checkoutData.razorpay_order_id,
        amount: checkoutData.amount,
        currency: checkoutData.currency,
        customer_name: checkoutData.customer_name,
        customer_email: checkoutData.customer_email,
        customer_phone: checkoutData.customer_phone,
        ride_request_id: checkoutData.ride_request_id,
      },
      {
        onDismiss: () => setPhase('cancelled'),
      },
    )

    if (result.cancelled) {
      setPhase('cancelled')
      return
    }
    if (result.error) {
      setError(result.error.message || 'Checkout failed to open.')
      setPhase('failed')
      return
    }

    // Checkout returned a payment — the backend must confirm it.
    setPhase('verifying')
    try {
      const verification = await paymentsApi.verify(result.response)
      if (verification?.verified && verification?.status === 'paid') {
        setPhase('paid')
        onPaid?.(verification)
        return
      }
      setError(verification?.message || 'Payment could not be verified.')
      setPhase('failed')
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' && detail ? detail : 'Payment verification failed.')
      setPhase('failed')
    }
  }

  const busy = phase === 'creating' || phase === 'paying' || phase === 'verifying'

  const label =
    phase === 'creating' ? 'Preparing payment…'
    : phase === 'paying' ? 'Complete payment in checkout'
    : phase === 'verifying' ? 'Verifying payment…'
    : phase === 'paid' ? 'Payment successful'
    : phase === 'cancelled' ? 'Payment cancelled — tap to retry'
    : phase === 'failed' ? 'Payment failed — tap to retry'
    : `Pay ${rideOptionName ? `· ${rideOptionName}` : ''}`

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <Button
        type="button"
        onClick={handlePay}
        disabled={disabled || busy || phase === 'paid'}
        size="lg"
        className={cn(
          'h-[52px] w-full text-[16px] uber-cta primary-action',
          phase === 'paid' && 'border-black bg-black text-white dark:border-white dark:bg-white dark:text-black',
        )}
      >
        {phase === 'creating' && <Loader2 className="h-4 w-4 animate-spin" />}
        {phase === 'paying' && <CreditCard className="h-4 w-4" />}
        {phase === 'verifying' && <Loader2 className="h-4 w-4 animate-spin" />}
        {phase === 'paid' && <CheckCircle2 className="h-4 w-4" />}
        {(phase === 'failed' || phase === 'cancelled' || phase === 'idle') && <CreditCard className="h-4 w-4" />}
        {label}
      </Button>
      {error && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-[#D93025]/25 bg-[#D93025]/10 px-3 py-2 text-[13px] text-[#D93025]"
        >
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  )
}
