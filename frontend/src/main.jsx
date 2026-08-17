import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App.jsx'
import './index.css'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!clerkPublishableKey) {
  throw new Error('VITE_CLERK_PUBLISHABLE_KEY is missing from frontend/.env or environment variables')
}

const isLocalDevelopment = ['localhost', '127.0.0.1'].includes(window.location.hostname)
const isProductionClerkKey = clerkPublishableKey.startsWith('pk_live_')

if (isLocalDevelopment && isProductionClerkKey) {
  // Clerk still needs to be initialized so its own dashboard configuration
  // can decide whether this origin is allowed. A production key is valid on
  // localhost when the origin has been configured in Clerk.
  console.warn(
    'A production Clerk publishable key is being used on localhost. A pk_test_ key is recommended for local development.',
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={clerkPublishableKey}
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
      afterSignOutUrl="/"
    >
      <App />
    </ClerkProvider>
  </React.StrictMode>,
)
