/**
 * Razorpay Checkout integration (browser side).
 *
 * SECURITY: this module only ever receives PUBLIC values — the Razorpay
 * Key ID (rzp_test_… or rzp_live_…), the Razorpay order ID, and the amount the
 * server computed. The Key Secret NEVER reaches the frontend: checkout is
 * opened with an order_id created on the backend, and the payment is only
 * trusted after the backend verifies the signature server-side.
 *
 * Script loading follows Razorpay's current recommendation: inject
 * https://checkout.razorpay.com/v1/checkout.js once, lazily, and reuse it.
 */

const RAZORPAY_CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

let scriptPromise = null

function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(window.Razorpay)
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${RAZORPAY_CHECKOUT_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve(window.Razorpay))
      existing.addEventListener('error', () => reject(new Error('Failed to load Razorpay Checkout')))
      return
    }
    const script = document.createElement('script')
    script.src = RAZORPAY_CHECKOUT_SRC
    script.async = true
    script.onload = () => resolve(window.Razorpay)
    script.onerror = () => {
      scriptPromise = null
      reject(new Error('Failed to load Razorpay Checkout'))
    }
    document.body.appendChild(script)
  })
  return scriptPromise
}

export const isRazorpayConfigured = () => Boolean(window.Razorpay)

/**
 * Open Razorpay Checkout.
 *
 * @param {object} checkoutData - Response of POST /payments/create-order
 *   (razorpay_key_id, razorpay_order_id, amount [paise], currency, customer_*).
 * @param {object} handlers - { onSuccess(resp), onFailure(err), onDismiss() }
 *   NOTE: onSuccess does NOT mean the payment is confirmed. The caller must
 *   still post resp to /payments/verify and only show success after the
 *   backend confirms (verified=true).
 * @param {object} [theme] - { theme: { color: '#000000' } } passed to Checkout.
 * @returns {Promise<{cancelled: boolean, error?: Error, response?: object}>}
 */
export async function openRazorpayCheckout(checkoutData, handlers, theme) {
  if (!checkoutData?.razorpay_order_id || !checkoutData?.razorpay_key_id) {
    handlers?.onFailure?.(new Error('Missing checkout configuration'))
    return { cancelled: false, error: new Error('Missing checkout configuration') }
  }

  let Razorpay
  try {
    Razorpay = await loadRazorpayScript()
  } catch (error) {
    handlers?.onFailure?.(error)
    return { cancelled: false, error }
  }

  return new Promise((resolve) => {
    let settled = false
    const finish = (result) => {
      if (settled) return
      settled = true
      resolve(result)
    }

    const options = {
      key: checkoutData.razorpay_key_id,
      order_id: checkoutData.razorpay_order_id,
      amount: checkoutData.amount,
      currency: checkoutData.currency,
      name: 'SmartRoute',
      description: 'Ride fare payment',
      prefill: {
        name: checkoutData.customer_name || '',
        email: checkoutData.customer_email || '',
        contact: checkoutData.customer_phone || '',
      },
      notes: checkoutData.ride_request_id
        ? { ride_request_id: String(checkoutData.ride_request_id) }
        : {},
      theme: theme?.theme || { color: '#000000' },
      handler: (response) => {
        handlers?.onSuccess?.(response)
        finish({ cancelled: false, response })
      },
      modal: {
        ondismiss: () => {
          handlers?.onDismiss?.()
          finish({ cancelled: true })
        },
      },
    }

    try {
      const rzp = new Razorpay(options)
      rzp.on('payment.failed', (resp) => {
        handlers?.onFailure?.(resp?.error || new Error('Payment failed'))
      })
      rzp.open()
    } catch (error) {
      handlers?.onFailure?.(error)
      finish({ cancelled: false, error })
    }
  })
}
