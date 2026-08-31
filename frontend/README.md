# SmartRouteAI Frontend

The frontend is a React 19 + Vite application providing three distinct interfaces: Passenger app, Driver dashboard, and Admin control panel. All interfaces communicate with the FastAPI backend via REST API and WebSockets.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Development](#development)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Key Features](#key-features)
- [Troubleshooting](#troubleshooting)
- [Building for Production](#building-for-production)

---

## Quick Start

```bash
# Install dependencies
npm install

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your values (VITE_CLERK_PUBLISHABLE_KEY, VITE_API_BASE_URL)

# Start development server
npm run dev
```

Open `http://localhost:5173` in your browser. The app will auto-reload on file changes.

---

## Development

### Run Locally

```bash
npm run dev
```

Vite dev server runs at `http://localhost:5173` by default.

### Code Quality

```bash
# Check for linting issues
npm run lint

# Fix some linting issues automatically
npm run lint -- --fix
```

### Building

```bash
# Production build
npm run build

# Preview the production build locally
npm run preview
```

The build output is in `dist/` — this is what gets deployed.

---

## Environment Variables

Create a `.env` file in the `frontend/` directory:

```env
# Clerk authentication
# Get this from your Clerk app settings: https://dashboard.clerk.com
VITE_CLERK_PUBLISHABLE_KEY=pk_test_replace_with_your_key

# Backend API URL
# Local development: http://localhost:8000
# Production: https://api.youromain.com
VITE_API_BASE_URL=http://localhost:8000
```

**Important Security Notes:**
- `VITE_*` variables are exposed in the browser bundle
- Never put database passwords, Clerk secret keys, or Supabase service-role keys here
- Stadia API key must stay in `backend/.env` only — frontend calls through the backend proxy
- Keep the backend URL separate from the Stadia key to maintain security

---

## Project Structure

```
frontend/
├── index.html                    # Entry HTML file
├── vite.config.js               # Vite configuration
├── eslint.config.js             # ESLint rules
├── package.json                 # Dependencies and scripts
│
├── public/                       # Static assets (favicon, images, etc.)
│
└── src/
    ├── index.css                # Global styles
    ├── swift.css                # App-specific styles
    ├── main.jsx                 # React entry point
    ├── App.jsx                  # Main router and page layout
    ├── SwiftApp.jsx             # App shell (sidebar, header, theme)
    │
    ├── views/                   # Full-page views (one per major section)
    │   ├── PassengerView.jsx    # Passenger ride booking + tracking
    │   ├── DriverView.jsx       # Driver dashboard + live tracking
    │   ├── AdminView.jsx        # Admin control panel (8 sections)
    │   ├── NotFoundView.jsx     # 404 page
    │   └── AuthLoadingView.jsx  # Loading state during auth init
    │
    ├── components/              # Reusable UI components
    │   ├── AppMap.jsx           # MapLibre map wrapper
    │   ├── Header.jsx           # Top navigation bar
    │   ├── Sidebar.jsx          # Left sidebar navigation
    │   └── [other components]   # Feature-specific components
    │
    ├── services/                # API communication layer
    │   └── api.js               # Axios instance + API methods
    │       ├── REST endpoints (rides, vehicles, clusters, routes, etc.)
    │       └── WebSocket factories (tracking, notifications)
    │
    ├── hooks/                   # Custom React hooks
    │   └── useWebSocket.js      # WebSocket connection management
    │
    ├── config/                  # Configuration and constants
    │   ├── demoPresets.js       # Demo data for testing
    │   └── [other configs]      # App constants, theme settings, etc.
    │
    ├── ui/                      # UI-related utilities
    │   └── [theme files, helpers]
    │
    └── assets/                  # Images, icons, etc.
```

---

## Key Features

### Passenger Interface

**Ride Booking:**
- Search and select destination using autocomplete
- Choose ride tier: SwiftX, SwiftXL, Lux Black, Moto
- Flat fare display before booking
- Estimated pickup time

**Trip Tracking:**
- Live vehicle position updates on map (every 5 seconds via WebSocket)
- Vehicle details: plate, driver name, rating
- ETA to destination
- Route polyline (when available)
- Trip status badge (pending, assigned, arriving, in_progress, completed)

**Trip History:**
- List of past trips
- Filter by status or date
- Trip details modal

**Notifications:**
- Ride status changes (assigned, vehicle arriving, completed)
- Server-sent via WebSocket `/notifications/ws`
- Badge counter in sidebar

### Driver Interface

**Fleet Dashboard:**
- Real-time fleet statistics
- Active vehicles, idle vehicles, total rides
- Utilization percentage

**Live Fleet Map:**
- All assigned vehicles on MapLibre
- WebSocket connection to `/tracking/ws` for live GPS updates
- Click vehicle for details

**Active Ride Management:**
- List of waypoints for assigned route
- Start / Arriving / Complete buttons for each ride
- Real-time customer notifications

**Location Sharing:**
- Continuous GPS streaming to backend
- Falls back to simulated coordinates if geolocation unavailable

### Admin Panel (8 Sections)

1. **Overview** — Fleet statistics, active routes, utilization %, demand heatmap preview
2. **Rides** — List all rides with status filter, manually advance ride status
3. **Fleet** — Create vehicles, assign drivers, set status, view GPS positions
4. **Cluster** — Run HDBSCAN clustering, view cluster history and summaries
5. **Routes** — Run VRP optimization, view waypoint details and maps
6. **Analytics** — Daily breakdown (7/14/30 day), bar chart + data table
7. **Jobs** — View background job status, manually trigger jobs, review history
8. **Heatmap** — XGBoost demand predictions visualized on MapLibre

---

## Troubleshooting

### Map Issues

**Map doesn't load or shows blank gray canvas:**
- Verify `VITE_API_BASE_URL` in `.env` is correct
- Verify backend is running: `curl http://localhost:8000/health/live`
- Check browser console (F12) for errors
- Verify `STADIA_API_KEY` is set in `backend/.env`

**"Cannot find module 'maplibre-gl-worker.mjs'":**
```bash
rm -rf node_modules package-lock.json
npm install
npm run dev -- --force
```

**Tiles don't load (checkered pattern):**
- This indicates the API key is invalid or the backend `/maps/style` endpoint is not returning valid Stadia style JSON
- Verify backend is forwarding requests to Stadia correctly

### Authentication Issues

**"Cannot read property 'auth' of undefined":**
- Clerk app is not initialized
- Check `VITE_CLERK_PUBLISHABLE_KEY` is set correctly in `.env`
- Verify the key belongs to your Clerk app, not another one
- Check Clerk Dashboard → API Keys to confirm the publishable key

**"User not found" or "401 Unauthorized" in API responses:**
- Clerk token is invalid or expired
- Sign out and sign back in: sidebar → user menu → Sign out
- Check browser DevTools → Application → Cookies for `__session` cookie

**Redirect loop between login and app:**
- Mismatch between Clerk configuration and environment variables
- Verify `VITE_CLERK_PUBLISHABLE_KEY` matches your Clerk app's publishable key
- Check Clerk Dashboard → Instances → Settings → Authorized URLs includes your frontend URL

### Performance & Build Issues

**Slow `npm install` or large node_modules:**
- Use `npm ci` instead of `npm install` for faster, deterministic installs
- Consider using `npm prune` to remove dev dependencies before deployment

**ESLint or TypeScript errors after updating React 19:**
- React 19 changes JSX syntax; some legacy rules may need updating
- Review eslint.config.js and update rules if needed
- Run `npm run lint -- --fix` to auto-fix some issues

**Vite showing "port 5173 already in use":**
```bash
# Kill the process using port 5173
# macOS/Linux:
lsof -i :5173 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Windows:
netstat -ano | findstr :5173
taskkill /PID <PID> /F
```

---

## Building for Production

### Pre-Build Checklist

1. ✅ Environment variables set correctly (check `.env` against `.env.example`)
2. ✅ Backend is running (to test API integration)
3. ✅ No console errors with `npm run dev`
4. ✅ `npm run lint` passes
5. ✅ All routes tested in dev browser

### Build Command

```bash
npm run build
```

Output is in `dist/` folder.

### Verify Production Build

```bash
npm run preview
```

Opens `http://localhost:4173` with the production build. Verify:
- All pages load
- Map displays correctly
- API requests work
- No 404 errors in console

### Deployment Options

**Docker:**
```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine
RUN npm install -g serve
WORKDIR /app
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
```

**Vercel/Netlify:**
- Build command: `npm run build`
- Output directory: `dist`
- Environment variables: Add `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_BASE_URL`

**AWS S3 + CloudFront:**
- Build with `npm run build`
- Upload `dist/` to S3 bucket
- Set CloudFront to origin and invalidate cache
- Update `VITE_API_BASE_URL` in build if needed

---

## API Integration

The frontend communicates with the backend via:

### REST API (Axios)
Located in `src/services/api.js`:
```javascript
// GET request
const rides = await api.get('/rides/my-rides');

// POST request
const newRide = await api.post('/rides/request', {
  from_lat, from_lng, to_lat, to_lng, tier
});

// PATCH request
await api.patch(`/rides/${rideId}`, { status: 'cancelled' });
```

### WebSocket (Real-time)
Located in `src/hooks/useWebSocket.js`:
```javascript
// Tracking updates (vehicle positions)
const trackingWS = useWebSocket('/tracking/ws');

// Notifications (ride status changes)
const notificationsWS = useWebSocket('/notifications/ws');
```

All WebSocket connections automatically:
- Manage Clerk JWT authentication via bearer subprotocol
- Reconnect on network failure (exponential backoff)
- Clean up on unmount

---

## State Management

Currently using React Context API + hooks for state. Key patterns:

- `useWebSocket` hook manages connection lifecycle
- Local component state for UI (loading, errors, modals)
- API methods fetch data on-demand
- Polling for periodic updates (ride status every 5s)

For larger state, consider adding Redux or Zustand (not currently in use).

---

## Contributing

1. **Create a feature branch**: `git checkout -b feature/my-feature`
2. **Follow code style**: ESLint config enforces consistency
3. **Test in dev**: `npm run dev` and verify all views
4. **Build and preview**: `npm run build && npm run preview`
5. **Commit and push**: Create a PR

Code style notes:
- Use functional components with hooks (no class components)
- Keep components small and focused (< 300 lines ideally)
- Use destructuring for props and imports
- Add comments for non-obvious logic
