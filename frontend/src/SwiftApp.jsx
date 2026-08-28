import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { SignIn, SignUp, useAuth, useClerk, useUser } from '@clerk/clerk-react'
import {
  loadAppBootstrap, clearAppBootstrap, setAuthTokenGetter,
  notificationsApi, authApi, createNotificationsWS,
} from './services/api.js'
import { C, s } from './ui/tokens.js'

// Keep role-specific screens (and their map/chart dependencies) out of the
// initial authentication bundle. Only the view for the signed-in role loads.
const PassengerView = lazy(() => import('./views/PassengerView'))
const DriverView = lazy(() => import('./views/DriverView'))
const AdminView = lazy(() => import('./views/AdminView'))
const PresentationDemoView = lazy(() => import('./views/PresentationDemoView'))

// ─── Constants ────────────────────────────────────────────────────────────────
const authInitStartedAt = Date.now()

function initialView() {
  const p = window.location.pathname
  if (p.startsWith('/sign-up')) return 'register'
  return 'login'
}

// ─── Design tokens ────────────────────────────────────────────────────────────
// ─── Toast system ─────────────────────────────────────────────────────────────
function ToastBar({ toasts, dismiss }) {
  const colors = { success:C.accent, warning:C.accent2, error:C.danger, info:'#60a5fa' }
  const icons  = { success:'✓', warning:'!', error:'✕', info:'i' }
  return (
    <div style={s({ position:'fixed', top:20, right:20, zIndex:9999, display:'flex', flexDirection:'column', gap:8, width:320, pointerEvents:'none' })}>
      {toasts.map(t => (
        <div key={t.id} className="toast-in" style={s({ pointerEvents:'all', display:'flex', gap:12, alignItems:'flex-start', background:C.surface, border:`1px solid ${C.border2}`, borderRadius:10, padding:'11px 13px', boxShadow:'0 8px 24px rgba(0,0,0,0.12)', borderLeft:`3px solid ${colors[t.type]}` })}>
          <div style={s({ width:22, height:22, borderRadius:6, background:colors[t.type]+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:800, color:colors[t.type], flexShrink:0 })}>{icons[t.type]}</div>
          <div style={{ flex:1, minWidth:0 }}>
            <p style={s({ color:C.text, fontSize:12, fontWeight:700, lineHeight:1.3 })}>{t.title}</p>
            {t.body && <p style={s({ color:C.muted2, fontSize:11, marginTop:2 })}>{t.body}</p>}
          </div>
          <button onClick={() => dismiss(t.id)} style={s({ color:C.muted, fontSize:12, background:'none', border:'none', cursor:'pointer', lineHeight:1 })}>✕</button>
        </div>
      ))}
    </div>
  )
}

// ─── Auth screens ─────────────────────────────────────────────────────────────
const clerkAppearance = {
  variables: { colorPrimary:'#00c9a7', colorBackground:'#0d1117', colorText:'#dde8f8', colorTextSecondary:'#7a90b0', colorInputBackground:'#111620', colorInputText:'#dde8f8', borderRadius:'10px' },
  elements: { card:'shadow-none', formButtonPrimary:'font-weight:700', footerAction:'color:#7a90b0' },
}

function AuthScreen({ view, onToggle, onGuestLogin }) {
  return (
    <div style={s({ minHeight:'100vh', background:C.bg, display:'flex', alignItems:'center', justifyContent:'center', padding:24 })}>
      <div style={s({ width:'100%', maxWidth:440 })}>
        
        {/* Brand Header */}
        <div style={s({ textAlign:'center', marginBottom:20 })}>
          <div style={s({ display:'inline-flex', alignItems:'center', gap:10, marginBottom:6 })}>
            <div style={s({ width:38, height:38, borderRadius:10, background:C.accent, color:C.bg2, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, fontWeight:800 })}>S</div>
            <span style={s({ fontFamily:'Bricolage Grotesque,sans-serif', fontSize:22, fontWeight:800, color:C.text, letterSpacing:'-0.03em' })}>SmartRoute AI</span>
          </div>
          <p style={s({ color:C.muted2, fontSize:12 })}>Autonomous Shared Transit Optimization Engine</p>
        </div>

        {/* Simulation mode chooser */}
        <div style={s({ background:`linear-gradient(135deg, ${C.surface} 0%, ${C.surface2} 100%)`, border:`1.5px solid ${C.accent}66`, borderRadius:14, padding:'14px 16px', marginBottom:20, boxShadow:'0 8px 24px rgba(0,201,167,0.15)' })}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
            <span style={s({ color:C.accent, fontSize:11, fontWeight:800, textTransform:'uppercase', letterSpacing:'0.06em' })}>Simulation Mode</span>
            <span style={{ fontSize:14 }}>⇄</span>
          </div>
          <p style={s({ color:C.muted2, fontSize:11, marginBottom:12, lineHeight:1.4 })}>
            Choose the normal Uber-like ride flow or the isolated college presentation walkthrough.
          </p>
          <div style={{ display:'flex', gap:7 }}>
            <button
              onClick={() => onGuestLogin?.('passenger', 'home')}
              style={s({ flex:1, padding:'10px 8px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:9, fontSize:11, fontWeight:800, cursor:'pointer' })}
            >
              🚕 Normal Ride
            </button>
            <button
              onClick={() => onGuestLogin?.('admin', 'presentation-demo')}
              style={s({ flex:1, padding:'10px 8px', background:`linear-gradient(135deg, ${C.accent} 0%, #00a887 100%)`, color:C.bg, border:'none', borderRadius:9, fontSize:11, fontWeight:800, cursor:'pointer', boxShadow:'0 4px 14px rgba(0,201,167,0.3)' })}
            >
              🎓 Presentation
            </button>
          </div>
        </div>

        {/* Quick Role Fast-Pass */}
        <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:'12px 14px', marginBottom:20 })}>
          <p style={s({ color:C.muted2, fontSize:10, fontWeight:700, textTransform:'uppercase', marginBottom:8, textAlign:'center' })}>Quick Role Login (One-Click Bypass)</p>
          <div style={{ display:'flex', gap:6 }}>
            <button onClick={() => onGuestLogin?.('passenger', 'home')} style={s({ flex:1, padding:'7px 8px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:7, fontSize:11, fontWeight:700, cursor:'pointer' })}>
              👤 Passenger
            </button>
            <button onClick={() => onGuestLogin?.('driver', 'driver-home')} style={s({ flex:1, padding:'7px 8px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:7, fontSize:11, fontWeight:700, cursor:'pointer' })}>
              🚗 Driver
            </button>
            <button onClick={() => onGuestLogin?.('admin', 'admin-overview')} style={s({ flex:1, padding:'7px 8px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:7, fontSize:11, fontWeight:700, cursor:'pointer' })}>
              🛡️ Admin
            </button>
          </div>
        </div>

        {/* Clerk Sign In / Sign Up Form */}
        <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:16 }}>
          <p style={s({ color:C.muted2, fontSize:11, textAlign:'center', marginBottom:12 })}>{view==='login' ? 'Or sign in with Clerk account' : 'Or create new Clerk account'}</p>
          {view==='login'
            ? <SignIn routing="hash" fallbackRedirectUrl="/" appearance={clerkAppearance} />
            : <SignUp routing="hash" fallbackRedirectUrl="/" appearance={clerkAppearance} />
          }
          <p style={s({ textAlign:'center', marginTop:16, color:C.muted, fontSize:12 })}>
            {view==='login' ? "Don't have an account? " : 'Already have an account? '}
            <button onClick={onToggle} style={s({ background:'none', border:'none', color:C.accent, fontWeight:700, cursor:'pointer', fontSize:12 })}>
              {view==='login' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        </div>

      </div>
    </div>
  )
}

// ─── Loading screen ───────────────────────────────────────────────────────────
function LoadingScreen({ timeout, onGuestLogin }) {
  return (
    <div style={s({ width:'100%', height:'100%', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:16, padding:24, textAlign:'center' })}>
      <div style={s({ width:44, height:44, borderRadius:'50%', border:`3px solid ${C.accent}30`, borderTopColor:C.accent, animation:'spin 0.8s linear infinite' })} />
      <p style={s({ color:C.muted, fontSize:13 })}>Loading SmartRoute AI…</p>
      
      {/* Fallback fast pass if Clerk is taking a while or blocked by Brave Shields */}
      <div style={s({ marginTop:12, maxWidth:360, padding:16, background:C.surface, border:`1px solid ${C.border}`, borderRadius:12 })}>
        <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:8 })}>Quick Simulation Access</p>
        <p style={s({ color:C.muted2, fontSize:11, lineHeight:1.4, marginBottom:12 })}>If authentication is slow or blocked, choose which isolated simulation to open:</p>
        <div style={{ display:'flex', gap:7 }}>
          <button
            onClick={() => onGuestLogin?.('passenger', 'home')}
            style={s({ flex:1, padding:'9px 8px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:8, fontSize:11, fontWeight:800, cursor:'pointer' })}
          >
            🚕 Normal Ride
          </button>
          <button
            onClick={() => onGuestLogin?.('admin', 'presentation-demo')}
            style={s({ flex:1, padding:'9px 8px', background:C.accent, color:C.bg, border:'none', borderRadius:8, fontSize:11, fontWeight:800, cursor:'pointer' })}
          >
            🎓 Presentation
          </button>
        </div>
      </div>
    </div>
  )
}

function BootstrapErrorScreen({ onRetry }) {
  return (
    <div style={s({ width:'100%', height:'100%', display:'flex', alignItems:'center', justifyContent:'center', padding:24, textAlign:'center' })}>
      <div style={s({ maxWidth:420, padding:24, background:C.surface, border:`1px solid ${C.border}`, borderRadius:12 })}>
        <p style={s({ color:C.danger, fontSize:15, fontWeight:800, marginBottom:8 })}>Unable to load your account</p>
        <p style={s({ color:C.muted2, fontSize:12, lineHeight:1.5, marginBottom:16 })}>The backend could not verify your session or load your profile. Try again after checking that the API is running.</p>
        <button onClick={onRetry} style={s({ background:C.accent, color:C.bg, border:'none', borderRadius:8, padding:'8px 16px', fontSize:12, fontWeight:700, cursor:'pointer' })}>Retry</button>
      </div>
    </div>
  )
}

// ─── Root App ─────────────────────────────────────────────────────────────────
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
            }
            setUser(u)
            const notifs = notifData?.notifications || []
            setNotifications(notifs)
            setView(roleHome(u.role))
            const unread = notifs.filter((n) => !n.is_read).length
            toast('success', `Welcome back, ${u.name.split(' ')[0]}!`, unread > 0 ? `${unread} unread notification${unread===1?'':'s'}` : '')
          })
          .catch(() => {
            fetchedRef.current = null
            setBootstrapError(true)
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

  // Keep the inbox and toast state in sync with ride lifecycle events.
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

  const isBootstrapping = isLoaded && isSignedIn && !user && !bootstrapError
  const isAuthView      = view === 'login' || view === 'register'
  const unreadCount     = notifications.filter((n) => !n.is_read).length

  return (
    <div style={s({ width:'100vw', height:'100vh', background:C.bg, overflow:'hidden', fontFamily:'Nunito,sans-serif' })}>
      <style>{`
        @keyframes spin  { to { transform:rotate(360deg) } }
        @keyframes fade-in { from { opacity:0; transform:translateY(6px) } to { opacity:1; transform:none } }
        .toast-in { animation: fade-in 0.2s ease }
        * { box-sizing:border-box; margin:0; padding:0 }
        button { font-family:inherit }
        input, textarea, select { font-family:inherit }
        ::-webkit-scrollbar { width:4px; height:4px }
        ::-webkit-scrollbar-track { background:transparent }
        ::-webkit-scrollbar-thumb { background:var(--border2); border-radius:4px }
      `}</style>

      <ToastBar toasts={toasts} dismiss={id => setToasts(p => p.filter(t => t.id !== id))} />

      {user
        ? <AppShell user={user} view={view} setView={setView} unreadCount={unreadCount} onLogout={handleLogout} notifications={notifications} setNotifications={setNotifications} toast={toast} />
        : (!isLoaded || isBootstrapping)
        ? <LoadingScreen timeout={authTimeout && !isBootstrapping} onGuestLogin={handleGuestLogin} />
        : bootstrapError
        ? <BootstrapErrorScreen onRetry={() => window.location.reload()} />
        : isAuthView
        ? <AuthScreen view={view} onToggle={() => setView(view==='login'?'register':'login')} onGuestLogin={handleGuestLogin} />
        : <LoadingScreen timeout={false} onGuestLogin={handleGuestLogin} />
      }
    </div>
  )
}

function roleHome(role) {
  if (role === 'admin')  return 'admin-overview'
  if (role === 'driver') return 'driver-home'
  return 'home'
}

// ─── App Shell ────────────────────────────────────────────────────────────────
function AppShell({ user, view, setView, unreadCount, onLogout, notifications, setNotifications, toast }) {
  const passengerNav = [
    { v:'home',              icon:'⌂', label:'Home' },
    { v:'trips',             icon:'▤', label:'My Trips' },
    { v:'inbox',             icon:'◉', label:'Inbox', badge:true },
    { v:'recent-rides',      icon:'◷', label:'Recent Rides' },
    { v:'profile',           icon:'○', label:'Profile' },
  ]
  const driverNav = [
    { v:'driver-home',       icon:'▣', label:'Dashboard' },
    { v:'presentation-demo', icon:'⚡', label:'Presentation Demo' },
    { v:'driver-map',        icon:'⌁', label:'Live Map' },
    { v:'driver-routes',     icon:'›', label:'My Routes' },
    { v:'inbox',             icon:'◉', label:'Inbox', badge:true },
    { v:'profile',           icon:'○', label:'Profile' },
  ]
  const adminNav = [
    { v:'admin-overview',    icon:'▦', label:'Overview' },
    { v:'presentation-demo', icon:'⚡', label:'Presentation Demo' },
    { v:'admin-rides',       icon:'▤', label:'Rides' },
    { v:'admin-vehicles',    icon:'□', label:'Fleet' },
    { v:'admin-cluster',     icon:'⌘', label:'Cluster' },
    { v:'admin-routes',      icon:'⌁', label:'Routes' },
    { v:'admin-analytics',   icon:'↗', label:'Analytics' },
    { v:'admin-jobs',        icon:'⚙', label:'Jobs' },
    { v:'admin-heatmap',     icon:'◌', label:'Heatmap' },
  ]
  const nav = user.role==='admin' ? adminNav : user.role==='driver' ? driverNav : passengerNav

  return (
    <div className="app-shell" style={s({ display:'flex', width:'100%', height:'100%' })}>
      {/* Sidebar */}
      <aside className="app-sidebar" style={s({ width:220, flexShrink:0, background:C.bg2, borderRight:`1px solid ${C.border}`, display:'flex', flexDirection:'column', padding:'20px 12px' })}>
        <div className="brand" style={s({ display:'flex', alignItems:'center', gap:10, marginBottom:28, paddingLeft:4 })}>
          <div style={s({ width:34, height:34, borderRadius:9, background:C.accent, color:C.bg2, display:'flex', alignItems:'center', justifyContent:'center', fontSize:15, fontWeight:800 })}>S</div>
          <div className="brand-copy">
            <p style={s({ color:C.text, fontSize:14, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>SmartRoute</p>
            <p style={s({ color:C.muted, fontSize:10, textTransform:'uppercase', letterSpacing:'0.1em' })}>{user.role}</p>
          </div>
        </div>
        <div style={s({ marginBottom:16, padding:8, background:C.surface, border:`1px solid ${C.border}`, borderRadius:10 })}>
            <p style={s({ color:C.muted2, fontSize:9, fontWeight:800, textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 3px 7px' })}>Simulation Mode</p>
            <div style={{ display:'flex', gap:4 }}>
              <button
                onClick={() => setView(roleHome(user.role))}
                style={s({ flex:1, padding:'7px 4px', border:'none', borderRadius:6, background:view === 'presentation-demo' ? 'transparent' : `${C.accent}22`, color:view === 'presentation-demo' ? C.muted2 : C.accent, fontSize:10, fontWeight:800, cursor:'pointer' })}
              >
                Normal
              </button>
              <button
                onClick={() => setView('presentation-demo')}
                style={s({ flex:1, padding:'7px 4px', border:'none', borderRadius:6, background:view === 'presentation-demo' ? `${C.accent}22` : 'transparent', color:view === 'presentation-demo' ? C.accent : C.muted2, fontSize:10, fontWeight:800, cursor:'pointer' })}
              >
                Demo
              </button>
            </div>
          </div>
        <nav style={{ flex:1, display:'flex', flexDirection:'column', gap:2 }}>
          {nav.map(item => {
            const active = view === item.v
            return (
              <button className="nav-item" key={item.v} onClick={() => setView(item.v)} style={s({ display:'flex', alignItems:'center', gap:10, padding:'9px 12px', borderRadius:9, border:'none', cursor:'pointer', background:active?`${C.accent}18`:'transparent', color:active?C.accent:C.muted2, fontSize:13, fontWeight:active?700:500, textAlign:'left', position:'relative' })}>
                <span style={{ fontSize:15 }}>{item.icon}</span>
                <span className="nav-label">{item.label}</span>
                {item.badge && unreadCount > 0 && (
                  <span style={s({ position:'absolute', right:10, background:C.danger, color:'#fff', fontSize:10, fontWeight:800, borderRadius:10, padding:'1px 5px', minWidth:18, textAlign:'center' })}>{unreadCount}</span>
                )}
              </button>
            )
          })}
        </nav>
        <div style={s({ borderTop:`1px solid ${C.border}`, paddingTop:12 })}>
          <div className="user-row" style={s({ display:'flex', alignItems:'center', gap:9, padding:'8px 12px', marginBottom:6 })}>
            <div style={s({ width:30, height:30, borderRadius:'50%', background:C.surface3, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:C.accent })}>{user.name.charAt(0).toUpperCase()}</div>
            <div className="user-copy" style={{ minWidth:0 }}>
              <p style={s({ color:C.text, fontSize:12, fontWeight:700, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' })}>{user.name}</p>
              <p style={s({ color:C.muted, fontSize:10, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' })}>{user.email}</p>
            </div>
          </div>
          <button onClick={onLogout} style={s({ width:'100%', padding:'8px 12px', background:'transparent', border:`1px solid ${C.border}`, borderRadius:8, color:C.muted2, fontSize:12, cursor:'pointer', textAlign:'left' })}><span className="sign-out-label">← Sign out</span><span className="sign-out-icon">←</span></button>
        </div>
      </aside>

      {/* Main — full height flex column so map views can fill all space */}
      <main className="app-main" style={s({ flex:1, overflow:'hidden', background:C.bg, display:'flex', flexDirection:'column', minHeight:0 })}>
        <RoleRouter user={user} view={view} setView={setView} notifications={notifications} setNotifications={setNotifications} toast={toast} />
      </main>
    </div>
  )
}

// ─── Role Router ──────────────────────────────────────────────────────────────
// Views that need full-height (contain maps)
const FULLHEIGHT_VIEWS = ['home','tracking','driver-map','driver-routes','presentation-demo']

function RoleRouter({ user, view, setView, notifications, setNotifications, toast }) {
  const ctx = { user, view, setView, toast }
  const fullH = FULLHEIGHT_VIEWS.includes(view)

  const inner = (() => {
    if (view === 'presentation-demo') return <PresentationDemoView {...ctx} />
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

// ─── Inbox ────────────────────────────────────────────────────────────────────
function InboxView({ notifications, setNotifications, toast }) {
  const markAll = async () => {
    try { await notificationsApi.markAllRead(); setNotifications(notifications.map((n) => ({...n, is_read:true}))); toast('success','All notifications marked as read') } catch (error) { void error }
  }
  const markOne = async (id) => {
    try { await notificationsApi.markRead(id); setNotifications(notifications.map((n) => n.id===id?{...n,is_read:true}:n)) } catch (error) { void error }
  }
  const typeIcon = { ride_requested:'🛻', ride_status_updated:'🔄', ride_cancelled:'❌', route_assigned:'📍', vehicle_tracking_update:'📡', system:'🔔' }
  return (
    <div style={s({ padding:28, maxWidth:760 })}>
      <div style={s({ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20 })}>
        <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>Notifications</h1>
        {notifications.some((n) => !n.is_read) && <button onClick={markAll} style={s({ background:C.surface2, border:`1px solid ${C.border2}`, color:C.accent, fontSize:12, fontWeight:700, borderRadius:8, padding:'7px 14px', cursor:'pointer' })}>Mark all read</button>}
      </div>
      {notifications.length === 0 && <p style={s({ color:C.muted, fontSize:14 })}>No notifications yet.</p>}
      <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
        {notifications.map((n) => (
          <div key={n.id} onClick={() => !n.is_read && markOne(n.id)} style={s({ display:'flex', gap:12, padding:'12px 14px', background:n.is_read?C.surface:C.surface2, border:`1px solid ${n.is_read?C.border:C.border2}`, borderRadius:10, cursor:n.is_read?'default':'pointer', transition:'background 0.15s' })}>
            <div style={s({ width:36, height:36, borderRadius:10, background:`${C.accent}15`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, flexShrink:0 })}>{typeIcon[n.notification_type] || '🔔'}</div>
            <div style={{ flex:1 }}>
              <p style={s({ color:C.text, fontSize:13, fontWeight:n.is_read?500:700 })}>{n.title}</p>
              <p style={s({ color:C.muted2, fontSize:12, marginTop:2 })}>{n.message}</p>
              <p style={s({ color:C.muted, fontSize:11, marginTop:4 })}>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</p>
            </div>
            {!n.is_read && <div style={s({ width:8, height:8, borderRadius:'50%', background:C.accent, flexShrink:0, marginTop:4 })} />}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Profile ──────────────────────────────────────────────────────────────────
function ProfileView({ user }) {
  const [saving, setSaving] = useState(false)
  const [name,  setName]  = useState(user.name)
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
    <div style={s({ padding:28, maxWidth:520 })}>
      <h1 style={s({ color:C.text, fontSize:20, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:24 })}>Profile</h1>
      <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:14, padding:24 })}>
        <div style={s({ display:'flex', alignItems:'center', gap:14, marginBottom:24 })}>
          <div style={s({ width:54, height:54, borderRadius:'50%', background:C.accent, display:'flex', alignItems:'center', justifyContent:'center', fontSize:22, fontWeight:800, color:C.bg })}>{user.name.charAt(0).toUpperCase()}</div>
          <div>
            <p style={s({ color:C.text, fontSize:16, fontWeight:700 })}>{user.name}</p>
            <p style={s({ color:C.muted, fontSize:12 })}>{user.email}</p>
            <span style={s({ fontSize:10, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.1em', color:C.accent, background:`${C.accent}18`, padding:'2px 7px', borderRadius:5 })}>{user.role}</span>
          </div>
        </div>
        {[{label:'Full Name',id:'name',val:name,set:setName},{label:'Phone',id:'phone',val:phone,set:setPhone}].map(f => (
          <div key={f.id} style={s({ marginBottom:16 })}>
            <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:6 })}>{f.label}</label>
            <input value={f.val} onChange={e=>f.set(e.target.value)} style={s({ width:'100%', padding:'10px 12px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:9, color:C.text, fontSize:13, outline:'none' })} />
          </div>
        ))}
        <div style={s({ marginBottom:16 })}>
          <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:6 })}>Email</label>
          <input value={user.email} disabled style={s({ width:'100%', padding:'10px 12px', background:C.bg2, border:`1px solid ${C.border}`, borderRadius:9, color:C.muted, fontSize:13, outline:'none' })} />
        </div>
        <button onClick={save} disabled={saving} style={s({ width:'100%', padding:'11px', background:C.accent, color:C.bg, border:'none', borderRadius:9, fontSize:13, fontWeight:700, cursor:'pointer' })}>
          {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}
