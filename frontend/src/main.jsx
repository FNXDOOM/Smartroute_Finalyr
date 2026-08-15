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
  throw new Error('VITE_CLERK_PUBLISHABLE_KEY is missing from frontend/.env.local')
}

const isLocalDevelopment = ['localhost', '127.0.0.1'].includes(window.location.hostname)
const isProductionClerkKey = clerkPublishableKey.startsWith('pk_live_')

if (isLocalDevelopment && isProductionClerkKey) {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <div style={{ maxWidth: 720, margin: '80px auto', padding: 24, fontFamily: 'system-ui', lineHeight: 1.6 }}>
      <h2>Clerk local development configuration required</h2>
      <p>The current Clerk production key is restricted to <code>fnxdoom.in</code>, so Clerk cannot load on localhost.</p>
      <p>Use a Clerk development key beginning with <code>pk_test_</code> in <code>frontend/.env</code>, or test this production key from its configured domain.</p>
    </div>
  )
} else {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <App />
      </ClerkProvider>
    </React.StrictMode>,
  )
}
