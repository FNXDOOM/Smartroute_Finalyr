import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App.jsx'
import './index.css'
import 'leaflet/dist/leaflet.css'

// Fix for default leaflet marker icon issue in React
import L from 'leaflet';
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});

L.Marker.prototype.options.icon = DefaultIcon;

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
