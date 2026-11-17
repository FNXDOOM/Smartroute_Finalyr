const KEY = 'smartroute-driver-onboarding'

export function beginDriverOnboarding(licensePlate = '') {
  sessionStorage.setItem(KEY, JSON.stringify({ licensePlate }))
}

export function getDriverOnboarding() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || 'null')
  } catch {
    return null
  }
}

export function clearDriverOnboarding() {
  sessionStorage.removeItem(KEY)
}
