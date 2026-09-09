import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { SignIn, SignUp, useAuth, useClerk, useUser } from '@clerk/clerk-react'
import {
  Bell, CarFront, CheckCircle2, ClipboardList, Flame, History, Home, Inbox, LayoutDashboard,
  Loader2, LogOut, Map as MapIcon, Route as RouteIcon, Settings, ShieldCheck, Sparkles,
  TriangleAlert, User as UserIcon, X, XCircle, Info, BarChart3, Truck, Zap, Play, GraduationCap,
} from 'lucide-react'
import {
  loadAppBootstrap, clearAppBootstrap, setAuthTokenGetter,
  notificationsApi, authApi, createNotificationsWS,
} from './services/api.js'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { ThemeToggle } from '@/components/theme-toggle'
import { useTheme } from '@/hooks/use-theme'
import AppTopBar from '@/components/AppTopBar'
import { PageHeader, DashboardEmptyState } from '@/components/dashboard-shared'

// Lazy-load role screens to slim auth bundle.
const PassengerView = lazy(() => import('./views/PassengerView'))
const DriverView = lazy(() => import('./views/DriverView'))
const AdminView = lazy(() => import('./views/AdminView'))
const PresentationDemoView = lazy(() => import('./views/PresentationDemoView'))
const DriverApplyView = lazy(() => import('./views/DriverApplyView'))

import DriverLoginForm from './components/DriverLoginForm.jsx'
import DriverVerificationGate from './components/DriverVerificationGate.jsx'

// Constants
const authInitStartedAt = Date.now()

// Route-icon brand mark.
function SmartRouteMark({ size = 18 }) {
  return <RouteIcon aria-hidden="true" size={size} strokeWidth={2.5} />
}

function initialView() {
  const p = window.location.pathname
  if (p.startsWith('/sign-up')) return 'register'
  return 'login'
}

// Toast system
function ToastBar({ toasts, dismiss }) {
  const styles = {
    success: { icon: CheckCircle2, cls: 'text-green-600 dark:text-green-400', bar: 'hsl(142 70% 35%)' },
    warning: { icon: TriangleAlert, cls: 'text-amber-500', bar: 'hsl(38 90% 50%)' },
    error: { icon: XCircle, cls: 'text-destructive', bar: 'hsl(var(--destructive))' },
    info: { icon: Info, cls: 'text-foreground', bar: 'hsl(var(--foreground))' },
  }
  return (
    <div className="pointer-events-none fixed right-4 top-16 z-[70] flex max-h-[calc(100vh-5rem)] w-[min(360px,calc(100vw-2rem))] flex-col gap-2 overflow-y-auto" role="status" aria-live="polite">
      {toasts.map((t) => {
        const S = styles[t.type] || styles.info
        const Icon = S.icon
        return (
          <Card key={t.id} className="toast-in pointer-events-auto overflow-hidden shadow-lg">
            <div className="h-0.5 w-full" style={{ background: S.bar }} />
            <CardContent className="flex items-start gap-3 p-3.5">
              <span className={cn('mt-0.5 shrink-0', S.cls)}><Icon className="h-5 w-5" aria-hidden="true" /></span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold leading-tight">{t.title}</p>
                {t.body && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t.body}</p>}
              </div>
              <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
                <X className="h-3.5 w-3.5" />
              </Button>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

// Auth screens
// Clerk needs explicit light/dark tokens.
function getClerkAppearance(theme) {
  const dark = theme === 'dark'
  return {
    variables: dark
      ? {
          colorPrimary: '#fafafa',
          colorBackground: '#141414',
          colorText: '#fafafa',
          colorTextSecondary: '#a3a3a3',
          colorInputBackground: '#1c1c1c',
          colorInputText: '#fafafa',
          borderRadius: '12px',
        }
      : {
          colorPrimary: '#111111',
          colorBackground: '#ffffff',
          colorText: '#111111',
          colorTextSecondary: '#555555',
          colorInputBackground: '#f5f5f5',
          colorInputText: '#111111',
          borderRadius: '12px',
        },
    elements: {
      card: 'shadow-none bg-transparent',
      footerAction: 'hidden',
      formButtonPrimary: 'font-weight:700',
      socialButtonsBlockButton: dark ? 'bg-[#1c2436] border border-[#33405a] text-[#e8eef7]' : undefined,
      socialButtonsBlockButtonText: dark ? 'text-[#e8eef7]' : undefined,
      formFieldLabel: dark ? 'text-[#a9b4c7]' : undefined,
      headerTitle: dark ? 'text-[#e8eef7]' : undefined,
      headerSubtitle: dark ? 'text-[#a9b4c7]' : undefined,
      footerActionText: dark ? 'text-[#a9b4c7]' : undefined,
    },
  }
}

function AuthScreen({ view, onToggle, onGuestLogin, theme, onToggleTheme, refreshAuthProfile }) {
  const [portal, setPortal] = useState('passenger') // 'passenger' | 'driver'

  return (
    <div className="auth-stage">
      <div className="auth-city" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
      <div className="auth-frame">
        <aside className="auth-intro">
          <div className="auth-intro-mark"><SmartRouteMark size={22} /></div>
          <p className="auth-kicker">SMART TRANSIT / 01</p>
          <h1>Smart<br />Transit</h1>
          <p className="auth-intro-copy">A calmer ride experience for passengers, drivers, and the teams coordinating every route.</p>
          <div className="auth-feature-panel">
            <div className="auth-feature-label"><span /> ROUTE INTELLIGENCE / LIVE</div>
            <div className="auth-feature-grid">
              <span>Demand forecast</span>
              <span>Shared matching</span>
              <span>Fleet visibility</span>
            </div>
          </div>
          <div className="auth-stat-row">
            <div><strong>0%</strong><span>surge pricing</span></div>
            <div><strong>24/7</strong><span>route intelligence</span></div>
          </div>
          <div className="auth-route-line"><span></span><i></i><span></span><i></i><span></span></div>
        </aside>
        <main className="auth-content">
          <div className="auth-content-inner">
        <div className="mb-5 flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow"><SmartRouteMark size={21} /></span>
            <span>
              <span className="block font-display text-[22px] font-extrabold leading-none tracking-tight">SmartRoute AI</span>
              <span className="mt-1 block text-xs text-muted-foreground">Autonomous Shared Transit Optimization Engine</span>
            </span>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>

        {/* Portal Switcher (Passenger vs Driver) */}
        <Tabs value={portal} onValueChange={setPortal} className="mb-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="passenger" activeValue={portal} onClick={() => setPortal('passenger')}>
              <UserIcon className="mr-1.5 h-3.5 w-3.5" /> Passenger Portal
            </TabsTrigger>
            <TabsTrigger value="driver" activeValue={portal} onClick={() => setPortal('driver')}>
              <CarFront className="mr-1.5 h-3.5 w-3.5" /> Driver Portal
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Simulation mode chooser */}
        <Card className="mb-4 border-primary/30 shadow-sm">
          <CardContent className="p-4">
            <div className="mb-2.5 flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-primary">Simulation Mode</span>
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => onGuestLogin?.('passenger', 'home')}>
                <Play className="h-3.5 w-3.5" /> Normal Ride
              </Button>
              <Button className="flex-1" onClick={() => onGuestLogin?.('admin', 'presentation-demo')}>
                <GraduationCap className="h-3.5 w-3.5" /> Presentation
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Quick Role Fast-Pass */}
        <Card className="mb-4">
          <CardContent className="p-3.5">
            <p className="mb-2 text-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Quick Role Login (One-Click Bypass)</p>
            <div className="flex gap-1.5">
              <Button variant="secondary" size="sm" className="flex-1" onClick={() => onGuestLogin?.('passenger', 'home')}>
                <UserIcon className="h-3.5 w-3.5" /> Passenger
              </Button>
              <Button variant="secondary" size="sm" className="flex-1" onClick={() => onGuestLogin?.('driver', 'driver-home')}>
                <CarFront className="h-3.5 w-3.5" /> Driver
              </Button>
              <Button variant="secondary" size="sm" className="flex-1" onClick={() => onGuestLogin?.('admin', 'admin-overview')}>
                <ShieldCheck className="h-3.5 w-3.5" /> Admin
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Dynamic Auth Body depending on active Portal */}
        {portal === 'driver' ? (
          <DriverLoginForm
            onSuccess={refreshAuthProfile}
            onSwitchToPassenger={() => setPortal('passenger')}
          />
        ) : (
          /* Clerk Passenger Sign In / Sign Up Form */
          <Card className="auth-passenger-card">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm uppercase tracking-wide text-primary">Passenger & Commuter Sign In</CardTitle>
                <Badge variant="secondary">Google OAuth + Pass</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {view === 'login'
                ? <SignIn key={`signin-${theme}`} routing="hash" fallbackRedirectUrl="/" appearance={getClerkAppearance(theme)} />
                : <SignUp key={`signup-${theme}`} routing="hash" fallbackRedirectUrl="/" appearance={getClerkAppearance(theme)} />
              }
              <p className="mt-4 text-center text-xs text-muted-foreground">
                {view === 'login' ? "Don't have an account? " : 'Already have an account? '}
                <button onClick={onToggle} className="font-semibold text-primary hover:underline">
                  {view === 'login' ? 'Sign up' : 'Sign in'}
                </button>
              </p>
            </CardContent>
          </Card>
        )}

          </div>
        </main>
      </div>
    </div>
  )
}

// Loading screen
function LoadingScreen({ onGuestLogin }) {
  return (
    <div className="loading-screen flex max-h-full min-h-0 h-full w-full flex-col items-center justify-center gap-4 overflow-y-auto p-6 text-center">
      <div className="loading-orbit" aria-hidden="true">
        <div className="loading-orbit-ring" />
        <div className="loading-orbit-core"><SmartRouteMark size={30} /></div>
      </div>
      <div className="loading-wordmark">SmartRoute <span>AI</span></div>
      <p className="loading-caption">Connecting intelligent routes...</p>
      <div className="flex w-full max-w-[360px] flex-col gap-2" aria-hidden="true">
        <Skeleton className="h-3 w-2/3 mx-auto opacity-40" />
        <Skeleton className="h-3 w-1/2 mx-auto opacity-30" />
      </div>

      {/* Fallback fast pass if Clerk is taking a while or blocked by Brave Shields */}
      <Card className="loading-access-card w-full max-w-[360px] text-left shadow-lg">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Quick Simulation Access</CardTitle>
          <CardDescription className="text-xs">If authentication is slow or blocked, choose which isolated simulation to open:</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onGuestLogin?.('passenger', 'home')}>
            <Play className="h-3.5 w-3.5" /> Normal Ride
          </Button>
          <Button className="flex-1" onClick={() => onGuestLogin?.('admin', 'presentation-demo')}>
            <GraduationCap className="h-3.5 w-3.5" /> Presentation
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function BootstrapErrorScreen({ onRetry, message }) {
  return (
    <div className="flex h-full w-full items-center justify-center overflow-y-auto p-6">
      <Empty className="w-full max-w-[420px] border bg-card shadow-sm">
        <EmptyHeader>
          <EmptyMedia variant="icon" className="bg-destructive/10 text-destructive">
            <XCircle className="h-4 w-4" />
          </EmptyMedia>
          <EmptyTitle>Unable to load your account</EmptyTitle>
          <EmptyDescription>{message || 'The backend could not verify your session or load your profile. Try again after checking that the API is running.'}</EmptyDescription>
        </EmptyHeader>
        <div className="flex w-full max-w-sm flex-col gap-2">
          <Button className="w-full" onClick={onRetry}>Retry</Button>
          <Button variant="ghost" className="w-full" onClick={() => window.location.reload()}>Reload page</Button>
        </div>
      </Empty>
    </div>
  )
}

// Root app
export default function App() {
  const [view, setView] = useState(initialView)
  const [user, setUser] = useState(null)
  const [toasts, setToasts] = useState([])
  const [notifications, setNotifications] = useState([])
  const [authTimeout, setAuthTimeout] = useState(false)
  const [bootstrapError, setBootstrapError] = useState(false)

  const { isLoaded, isSignedIn, getToken } = useAuth()
  const { user: clerkUser } = useUser()
  const { signOut } = useClerk()

  const getTokenRef = useRef(getToken)
  useEffect(() => { getTokenRef.current = getToken })
  const clerkUserId  = clerkUser?.id ?? null
  const clerkUserRef = useRef(clerkUser)
  useEffect(() => { clerkUserRef.current = clerkUser }, [clerkUser])
  const fetchedRef   = useRef(null)

  // Auth timeout indicator
  useEffect(() => {
    if (isLoaded) return
    const elapsed = Date.now() - authInitStartedAt
    const t = setTimeout(() => { if (!isLoaded) setAuthTimeout(true) }, Math.max(1000, 8000 - elapsed))
    return () => clearTimeout(t)
  }, [isLoaded])

  const toast = useCallback((type, title, body = '') => {
    const id = Math.random().toString(36).slice(2)
    setToasts(p => [...p, { id, type, title, body }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4500)
  }, [])

  const handleLogout = useCallback(async () => {
    if (fetchedRef.current) clearAppBootstrap(fetchedRef.current)
    fetchedRef.current = null
    setAuthTokenGetter(null)
    setUser(null)
    setBootstrapError(false)
    setNotifications([])
    setView('login')
    await signOut()
  }, [signOut])

  // Refresh profile and route to role home.
  const refreshAuthProfile = useCallback(async (targetView) => {
    const uid = clerkUserRef.current?.id
    if (!uid) return
    try {
      const [profile] = await loadAppBootstrap(uid)
      const cu = clerkUserRef.current
      const u = {
        id: cu?.id || '', name: profile.name || cu?.fullName || cu?.firstName || 'User',
        email: profile.email || cu?.primaryEmailAddress?.emailAddress || '',
        phone: profile.phone || cu?.primaryPhoneNumber?.phoneNumber || '',
        role: profile.role || cu?.publicMetadata?.role || 'passenger',
        driver_status: profile.driver_status || cu?.publicMetadata?.driver_status || 'active',
      }
      setUser(u)
      setView(targetView || roleHome(u.role))
    } catch { /* keep existing state; background bootstrap already ran once */ }
  }, [])

  // Bootstrap on sign-in
  useEffect(() => {
    if (!isLoaded) return
    if (isSignedIn && clerkUserId) {
      if (fetchedRef.current === clerkUserId) return
      fetchedRef.current = clerkUserId
      setBootstrapError(false)
      setAuthTokenGetter(() => getTokenRef.current());
      (async () => {
        let token = null
        for (let i = 0; i < 3; i++) {
          token = await getTokenRef.current()
          if (token) break
          await new Promise(r => setTimeout(r, 500*(i+1)))
        }
        const cu = clerkUserRef.current
        const fallbackUser = {
          id: cu?.id || '', name: cu?.fullName || cu?.firstName || 'User',
          email: cu?.primaryEmailAddress?.emailAddress || '',
          phone: cu?.primaryPhoneNumber?.phoneNumber || '',
          role: cu?.publicMetadata?.role || 'passenger',
          driver_status: cu?.publicMetadata?.driver_status || 'active',
        }
        if (!token) {
          fetchedRef.current = null
          setBootstrapError(true)
          return
        }
        loadAppBootstrap(clerkUserId)
          .then(([profile, , notifData]) => {
            const u = {
              id: cu?.id || '', name: profile.name || fallbackUser.name,
              email: profile.email || fallbackUser.email,
              phone: profile.phone || fallbackUser.phone,
              role: profile.role || fallbackUser.role,
              driver_status: profile.driver_status || fallbackUser.driver_status,
            }
            setUser(u)
            const notifs = notifData?.notifications || []
            setNotifications(notifs)
            setView(roleHome(u.role))
            const unread = notifs.filter((n) => !n.is_read).length
            toast('success', `Welcome back, ${u.name.split(' ')[0]}!`, unread > 0 ? `${unread} unread notification${unread===1?'':'s'}` : '')
          })
          .catch((err) => {
            fetchedRef.current = null
            const detail = err?.response?.data?.detail
            setBootstrapError(typeof detail === 'string' && detail ? detail : true)
          })
      })()
    } else if (isLoaded && !isSignedIn) {
      queueMicrotask(() => {
        setUser(null)
        setBootstrapError(false)
      })
      fetchedRef.current = null
    }
  }, [isLoaded, isSignedIn, clerkUserId, toast])

  // Sync inbox and toasts with ride events.
  const userId = user?.id
  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return
    let ws = null
    let cancelled = false
    getTokenRef.current().then(token => {
      if (!token || cancelled) return
      ws = createNotificationsWS(token, (message) => {
        const notification = message?.notification
        if (!notification) return
        setNotifications(prev => [notification, ...prev.filter(n => n.id !== notification.id)].slice(0, 50))
        toast('info', notification.title, notification.message)
      })
    }).catch((error) => { void error })
    return () => { cancelled = true; ws?.close() }
  }, [isLoaded, isSignedIn, userId, toast])

  const handleGuestLogin = useCallback((role = 'admin', targetView = 'presentation-demo') => {
    const guestUser = {
      id: 1,
      name: role === 'admin' ? 'Demo Admin (CIT)' : role === 'driver' ? 'Demo Driver (Rajesh)' : 'Demo Rider (Ananya)',
      email: `${role}@smartroute.ai`,
      phone: '+91 98765 43210',
      role: role,
    }
    setUser(guestUser)
    setView(targetView)
    toast('success', `Welcome, ${guestUser.name}!`, 'All transit simulations and features are active.')
  }, [toast])

  // Guard views by role.
  const safeSetView = useCallback((targetView) => {
    if (!user) {
      setView(targetView)
      return
    }

    const driverOnlyViews = ['driver-home', 'driver-map', 'driver-routes']
    const adminOnlyViews = ['admin-overview', 'admin-rides', 'admin-vehicles', 'admin-cluster', 'admin-routes', 'admin-analytics', 'admin-jobs', 'admin-heatmap', 'admin-drivers']

    if (user.role === 'passenger' && (driverOnlyViews.includes(targetView) || adminOnlyViews.includes(targetView))) {
      toast('warning', 'Role Guard Enforced', 'Driver or Administrator credentials required to access this portal.')
      setView('home')
      return
    }

    if (user.role === 'driver' && adminOnlyViews.includes(targetView)) {
      toast('warning', 'Admin Guard Enforced', 'Administrator credentials required.')
      setView('driver-home')
      return
    }

    setView(targetView)
  }, [user, toast])

  const isBootstrapping = isLoaded && isSignedIn && !user && !bootstrapError
  const isAuthView      = view === 'login' || view === 'register'
  const unreadCount     = notifications.filter((n) => !n.is_read).length
  const { theme, toggle: toggleTheme } = useTheme()

  return (
    <TooltipProvider delay={100}>
    <div className="h-dvh w-screen overflow-hidden bg-background font-sans text-foreground">
      <ToastBar toasts={toasts} dismiss={id => setToasts(p => p.filter(t => t.id !== id))} />

      {user
        ? (user.role === 'driver' && user.driver_status === 'pending_verification'
            ? <DriverVerificationGate
                user={user}
                onRefreshProfile={(updated) => setUser(prev => ({ ...prev, ...updated }))}
                onLogout={handleLogout}
                toast={toast}
              />
            : <AppShell user={user} view={view} setView={safeSetView} unreadCount={unreadCount} onLogout={handleLogout} notifications={notifications} setNotifications={setNotifications} toast={toast} theme={theme} onToggleTheme={toggleTheme} onRefreshProfile={refreshAuthProfile} />
          )
        : (!isLoaded || isBootstrapping)
        ? <LoadingScreen timeout={authTimeout && !isBootstrapping} onGuestLogin={handleGuestLogin} />
        : bootstrapError
        ? <BootstrapErrorScreen onRetry={() => window.location.reload()} message={typeof bootstrapError === 'string' ? bootstrapError : undefined} />
        : isAuthView
        ? <AuthScreen view={view} onToggle={() => setView(view==='login'?'register':'login')} onGuestLogin={handleGuestLogin} theme={theme} onToggleTheme={toggleTheme} refreshAuthProfile={refreshAuthProfile} />
        : <LoadingScreen timeout={false} onGuestLogin={handleGuestLogin} />
      }
    </div>
    </TooltipProvider>
  )
}

function roleHome(role) {
  if (role === 'admin')  return 'admin-overview'
  if (role === 'driver') return 'driver-home'
  return 'home'
}

// App shell
// Sidebar, TopBar, mobile nav; logic unchanged.
function AppShell({ user, view, setView, unreadCount, onLogout, notifications, setNotifications, toast, theme, onToggleTheme, onRefreshProfile }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  const passengerSections = [
    {
      label: 'Ride',
      items: [
        { v: 'home', Icon: Home, label: 'Home' },
        { v: 'trips', Icon: ClipboardList, label: 'My Trips' },
        { v: 'recent-rides', Icon: History, label: 'Recent Rides' },
      ],
    },
    {
      label: 'Account',
      items: [
        { v: 'inbox', Icon: Inbox, label: 'Inbox', badge: true },
        { v: 'profile', Icon: UserIcon, label: 'Profile' },
      ],
    },
  ]
  const driverSections = [
    {
      label: 'Drive',
      items: [
        { v: 'driver-home', Icon: LayoutDashboard, label: 'Dashboard' },
        { v: 'driver-map', Icon: MapIcon, label: 'Live Map' },
        { v: 'driver-routes', Icon: RouteIcon, label: 'My Routes' },
      ],
    },
    {
      label: 'Workspace',
      items: [
        { v: 'presentation-demo', Icon: Zap, label: 'Presentation Demo' },
        { v: 'inbox', Icon: Inbox, label: 'Inbox', badge: true },
        { v: 'profile', Icon: UserIcon, label: 'Profile' },
      ],
    },
  ]
  const adminSections = [
    {
      label: 'Operate',
      items: [
        { v: 'admin-overview', Icon: LayoutDashboard, label: 'Overview' },
        { v: 'admin-rides', Icon: ClipboardList, label: 'Rides' },
        { v: 'admin-vehicles', Icon: Truck, label: 'Fleet' },
        { v: 'admin-drivers', Icon: CarFront, label: 'Drivers' },
      ],
    },
    {
      label: 'Optimize',
      items: [
        { v: 'admin-cluster', Icon: RouteIcon, label: 'Cluster' },
        { v: 'admin-routes', Icon: MapIcon, label: 'Routes' },
        { v: 'admin-analytics', Icon: BarChart3, label: 'Analytics' },
      ],
    },
    {
      label: 'System',
      items: [
        { v: 'presentation-demo', Icon: Zap, label: 'Presentation Demo' },
        { v: 'admin-jobs', Icon: Settings, label: 'Jobs' },
        { v: 'admin-heatmap', Icon: Flame, label: 'Heatmap' },
      ],
    },
  ]
  const sections = user.role === 'admin' ? adminSections : user.role === 'driver' ? driverSections : passengerSections
  const isDemo = view === 'presentation-demo'

  const go = (v) => {
    setMobileOpen(false)
    setView(v)
  }

  const sidebarBody = (
    <>
      <div className="brand mb-5 flex items-center gap-2.5 px-1">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm"><SmartRouteMark size={18} /></span>
        <div className="brand-copy min-w-0 flex-1">
          <p className="text-sm font-extrabold leading-none tracking-tight">SmartRoute</p>
          <p className="mt-1 text-[11px] text-muted-foreground">Shared transit ops</p>
        </div>
        <Badge variant="secondary" className="shrink-0 text-[10px] uppercase">{user.role}</Badge>
      </div>

      <Card className="mb-4 shadow-sm">
        <CardContent className="p-2.5">
          <p className="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Simulation mode</p>
          <div className="grid grid-cols-2 gap-1.5" role="group" aria-label="Simulation mode">
            <Button
              variant={!isDemo ? 'default' : 'ghost'}
              size="sm"
              className="w-full"
              onClick={() => go(roleHome(user.role))}
              aria-pressed={!isDemo}
            >
              Normal
            </Button>
            <Button
              variant={isDemo ? 'default' : 'ghost'}
              size="sm"
              className="w-full"
              onClick={() => go('presentation-demo')}
              aria-pressed={isDemo}
            >
              <Zap className="h-3.5 w-3.5" /> Demo
            </Button>
          </div>
        </CardContent>
      </Card>

      <nav className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-0.5" aria-label="Primary">
        {sections.map((section) => (
          <div key={section.label}>
            <p className="nav-label mb-1.5 px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              {section.label}
            </p>
            <div className="flex flex-col gap-0.5">
              {section.items.map((item) => {
                const active = view === item.v
                const Icon = item.Icon
                return (
                  <Button
                    key={item.v}
                    variant={active ? 'secondary' : 'ghost'}
                    className={cn(
                      'nav-item h-9 w-full justify-start gap-2.5 px-2.5 font-medium',
                      active && 'bg-secondary font-semibold shadow-[inset_2px_0_0_hsl(var(--primary))]',
                    )}
                    onClick={() => go(item.v)}
                    aria-current={active ? 'page' : undefined}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="nav-label flex-1 truncate text-left text-[13px]">{item.label}</span>
                    {item.badge && unreadCount > 0 && (
                      <Badge variant="destructive" className="ml-auto h-5 min-w-5 px-1.5 text-[10px]">{unreadCount > 9 ? '9+' : unreadCount}</Badge>
                    )}
                  </Button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      <Separator className="my-3" />
      <button
        onClick={() => go('profile')}
        className="user-row mb-2 flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Avatar className="h-8 w-8 shrink-0">
          <AvatarFallback className="bg-primary/10 text-xs font-bold text-primary">{(user.name || 'U').charAt(0).toUpperCase()}</AvatarFallback>
        </Avatar>
        <div className="user-copy min-w-0 flex-1">
          <p className="truncate text-xs font-semibold">{user.name}</p>
          <p className="truncate text-[11px] text-muted-foreground">{user.email}</p>
        </div>
      </button>
      <Button variant="outline" className="w-full justify-start gap-2" onClick={onLogout}>
        <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" /><span className="sign-out-label">Sign out</span>
      </Button>
    </>
  )

  return (
    <div className="app-shell flex h-full w-full bg-background">
      {/* Desktop sidebar */}
      <aside className="app-sidebar hidden w-[248px] shrink-0 flex-col border-r bg-card px-3 py-5 md:flex">
        {sidebarBody}
      </aside>

      {/* Mobile nav */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="flex w-[280px] flex-col px-3 py-5">
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
          </SheetHeader>
          {sidebarBody}
        </SheetContent>
      </Sheet>

      {/* Main column with professional top bar */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <AppTopBar
          user={user}
          view={view}
          setView={setView}
          unreadCount={unreadCount}
          notifications={notifications}
          onOpenNotifications={() => setView('inbox')}
          onLogout={onLogout}
          onOpenMobileNav={() => setMobileOpen(true)}
          theme={theme}
          onToggleTheme={onToggleTheme}
        />
        <main className="app-main flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
          <RoleRouter user={user} view={view} setView={setView} notifications={notifications} setNotifications={setNotifications} toast={toast} onRefreshProfile={onRefreshProfile} />
        </main>
      </div>
    </div>
  )
}

// Role router
// Full-height views have maps
const FULLHEIGHT_VIEWS = ['home','tracking','driver-map','driver-routes','presentation-demo']

function RoleRouter({ user, view, setView, notifications, setNotifications, toast, onRefreshProfile }) {
  const ctx = { user, view, setView, toast }
  const fullH = FULLHEIGHT_VIEWS.includes(view)

  const inner = (() => {
    if (view === 'presentation-demo') return <PresentationDemoView {...ctx} />
    if (view === 'driver-apply') return <DriverApplyView {...ctx} onApplied={onRefreshProfile} />
    if (view === 'inbox')   return <InboxView notifications={notifications} setNotifications={setNotifications} toast={toast} />
    if (view === 'profile') return <ProfileView user={user} />
    if (user.role === 'passenger') return <PassengerView {...ctx} />
    if (user.role === 'driver')    return <DriverView {...ctx} />
    if (user.role === 'admin')     return <AdminView {...ctx} />
    return null
  })()

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow: fullH ? 'hidden' : 'auto' }}>
      <Suspense fallback={<LoadingScreen timeout={false} />}>
        {inner}
      </Suspense>
    </div>
  )
}

// Inbox
function InboxView({ notifications, setNotifications, toast }) {
  const markAll = async () => {
    try { await notificationsApi.markAllRead(); setNotifications(notifications.map((n) => ({ ...n, is_read: true }))); toast('success', 'All notifications marked as read') } catch (error) { void error }
  }
  const markOne = async (id) => {
    try { await notificationsApi.markRead(id); setNotifications(notifications.map((n) => (n.id === id ? { ...n, is_read: true } : n))) } catch (error) { void error }
  }
  const unread = notifications.filter((n) => !n.is_read).length
  return (
    <div className="mx-auto w-full max-w-[760px] space-y-4 p-4 md:p-7">
      <PageHeader
        title="Notifications"
        description={notifications.length ? `${unread} unread · ${notifications.length} total` : 'Workspace inbox'}
        actions={unread > 0 ? <Button variant="outline" size="sm" onClick={markAll}><CheckCircle2 className="h-3.5 w-3.5" /> Mark all read</Button> : undefined}
      />
      {notifications.length === 0 && (
        <DashboardEmptyState icon={Bell} title="No notifications yet" hint="Ride updates, dispatch events and driver approvals will appear here." />
      )}
      <div className="flex flex-col gap-2">
        {notifications.map((n) => (
          <Card
            key={n.id}
            onClick={() => !n.is_read && markOne(n.id)}
            onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !n.is_read) { e.preventDefault(); markOne(n.id) } }}
            tabIndex={!n.is_read ? 0 : undefined}
            role={!n.is_read ? 'button' : undefined}
            className={cn(
              'shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              !n.is_read && 'cursor-pointer border-primary/30 bg-primary/[0.04] hover:bg-primary/[0.07]',
            )}
          >
            <CardContent className="flex items-start gap-3 p-3.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10"><Bell className="h-4 w-4 text-primary" aria-hidden="true" /></span>
              <div className="min-w-0 flex-1">
                <p className={cn('text-[13px] leading-tight', !n.is_read ? 'font-bold' : 'font-medium')}>{n.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{n.message}</p>
                <p className="mt-1 text-[11px] text-muted-foreground/70">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</p>
              </div>
              {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

// Profile
function ProfileView({ user }) {
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState(user.name)
  const [phone, setPhone] = useState(user.phone)
  const [saved, setSaved] = useState(false)
  const save = async () => {
    setSaving(true)
    try {
      await authApi.updateProfile({ name, phone })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (error) { void error } finally { setSaving(false) }
  }
  return (
    <div className="mx-auto w-full max-w-[560px] space-y-5 p-4 md:p-7">
      <PageHeader title="Profile" description="How you appear to dispatch and riders" />
      <Card className="shadow-sm">
        <CardContent className="p-6">
          <div className="mb-6 flex items-center gap-3.5">
            <Avatar className="h-14 w-14">
              <AvatarFallback className="bg-primary text-xl font-extrabold text-primary-foreground">{(user.name || 'U').charAt(0).toUpperCase()}</AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="truncate text-base font-bold">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              <Badge className="mt-1.5 uppercase" variant="secondary">{user.role}</Badge>
            </div>
          </div>
          <div className="mb-4 space-y-1.5">
            <Label htmlFor="profile-name">Full name</Label>
            <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          </div>
          <div className="mb-4 space-y-1.5">
            <Label htmlFor="profile-phone">Phone</Label>
            <Input id="profile-phone" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" inputMode="tel" />
          </div>
          <div className="mb-5 space-y-1.5">
            <Label htmlFor="profile-email">Email</Label>
            <Input id="profile-email" value={user.email} disabled className="opacity-60" />
          </div>
          <Button className="w-full" onClick={save} disabled={saving}>
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</> : saved ? <><CheckCircle2 className="h-4 w-4" /> Saved</> : 'Save changes'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
