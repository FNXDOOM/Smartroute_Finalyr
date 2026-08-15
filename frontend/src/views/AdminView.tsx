import { useState, useEffect, useCallback } from 'react'
import { C, s, AppUser, View, Toast } from '../SwiftApp'
import {
  ridesApi, vehiclesApi, clusterApi, routeApi,
  analyticsApi, jobsApi, predictApi, trackingApi,
} from '../services/api.js'
import AppMap from '../components/AppMap'

interface Props { user:AppUser; view:View; setView:(v:View)=>void; toast:(t:Toast['type'],title:string,body?:string)=>void }

// ─── Shared helpers ───────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string,string> = {
  pending:'#f59e0b', clustered:'#a78bfa', assigned:'#60a5fa', arriving:'#00c9a7',
  in_progress:'#00c9a7', completed:'#22c55e', cancelled:'#f43f5e',
  idle:'#7a90b0', active:'#00c9a7', en_route:'#60a5fa', offline:'#f43f5e',
  solved:'#22c55e', clustered_status:'#a78bfa', no_pending_requests:'#7a90b0',
}
function Badge({ val }: { val:string }) {
  const col = STATUS_COLOR[val] || '#7a90b0'
  return <span style={s({ fontSize:10, fontWeight:700, textTransform:'uppercase', color:col, background:col+'22', padding:'2px 7px', borderRadius:5, flexShrink:0, letterSpacing:'0.07em' })}>{val.replace(/_/g,' ')}</span>
}
function Btn({ label, color=C.accent, onClick, disabled=false, small=false }: any) {
  return <button onClick={onClick} disabled={disabled} style={s({ padding: small?'6px 12px':'9px 16px', background:`${color}22`, border:`1px solid ${color}55`, color, fontSize:small?11:12, fontWeight:700, borderRadius:7, cursor:disabled?'not-allowed':'pointer', opacity:disabled?0.5:1 })}>{label}</button>
}
function StatCard({ label, val, icon, col }: { label:string; val:string|number; icon:string; col:string }) {
  return (
    <div style={s({ flex:'1 1 150px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:'16px 18px' })}>
      <div style={s({ display:'flex', justifyContent:'space-between' })}>
        <p style={s({ color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.07em' })}>{label}</p>
        <span style={{ fontSize:16 }}>{icon}</span>
      </div>
      <p style={s({ color:col, fontSize:26, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginTop:8 })}>{val}</p>
    </div>
  )
}
function PageHeader({ title, back, onBack }: { title:string; back?:string; onBack?:()=>void }) {
  return (
    <div style={s({ display:'flex', alignItems:'center', gap:12, marginBottom:24 })}>
      {back && <button onClick={onBack} style={s({ background:'none', border:'none', color:C.muted2, cursor:'pointer', fontSize:13 })}>← {back}</button>}
      <h1 style={s({ color:C.text, fontSize:22, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif' })}>{title}</h1>
    </div>
  )
}

// ─── Root admin router ────────────────────────────────────────────────────────
export default function AdminView({ user, view, setView, toast }: Props) {
  const ctx = { setView, toast }
  if (view === 'admin-rides')     return <RidesPanel     {...ctx} />
  if (view === 'admin-vehicles')  return <VehiclesPanel  {...ctx} />
  if (view === 'admin-cluster')   return <ClusterPanel   {...ctx} />
  if (view === 'admin-routes')    return <RoutesPanel    {...ctx} />
  if (view === 'admin-analytics') return <AnalyticsPanel {...ctx} />
  if (view === 'admin-jobs')      return <JobsPanel      {...ctx} />
  if (view === 'admin-heatmap')   return <HeatmapPanel   {...ctx} />
  return <OverviewPanel user={user} {...ctx} />
}

// ─── Overview Panel ───────────────────────────────────────────────────────────
function OverviewPanel({ user, setView, toast }: any) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsApi.overview()
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { toast('error','Failed to load overview'); setLoading(false) })
  }, [])

  if (loading) return <div style={s({ padding:28 })}><p style={s({ color:C.muted, fontSize:13 })}>Loading…</p></div>

  const byStatus = data?.rides_by_status || {}
  return (
    <div style={s({ padding:28 })}>
      <h1 style={s({ color:C.text, fontSize:22, fontWeight:800, fontFamily:'Bricolage Grotesque,sans-serif', marginBottom:4 })}>Admin Overview</h1>
      <p style={s({ color:C.muted, fontSize:13, marginBottom:24 })}>Welcome, {user.name} · Last updated: {data?.generated_at ? new Date(data.generated_at).toLocaleTimeString() : '—'}</p>

      <div style={s({ display:'flex', gap:12, flexWrap:'wrap', marginBottom:24 })}>
        <StatCard label="Total Rides"    val={data?.total_rides||0}          icon="🛻" col={C.accent} />
        <StatCard label="Vehicles"       val={data?.total_vehicles||0}        icon="🚗" col="#60a5fa" />
        <StatCard label="Active"         val={data?.active_vehicles||0}       icon="📡" col={C.accent} />
        <StatCard label="Idle"           val={data?.idle_vehicles||0}         icon="🔋" col={C.muted2} />
        <StatCard label="Cluster Runs"   val={data?.total_cluster_runs||0}    icon="🔬" col={C.accent3} />
        <StatCard label="Route Plans"    val={data?.total_route_plans||0}     icon="📍" col={C.accent2} />
      </div>

      <div style={s({ display:'flex', gap:16, flexWrap:'wrap', marginBottom:24 })}>
        <div style={s({ flex:'1 1 320px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:12 })}>Rides by Status</p>
          {Object.entries(byStatus).map(([st, cnt]:any) => (
            <div key={st} style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'7px 0', borderBottom:`1px solid ${C.border}` })}>
              <Badge val={st} />
              <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>{cnt}</p>
            </div>
          ))}
        </div>
        <div style={s({ flex:'1 1 280px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:12 })}>Metrics</p>
          {[
            ['Avg trip distance',   data?.avg_trip_distance_meters   ? `${(data.avg_trip_distance_meters/1000).toFixed(2)} km` : '—'],
            ['Avg route distance',  data?.avg_route_distance_meters  ? `${(data.avg_route_distance_meters/1000).toFixed(2)} km` : '—'],
            ['Avg passengers/stop', String(data?.avg_passengers_per_virtual_stop||0)],
            ['Route utilisation',   `${data?.route_utilization_percent||0}%`],
            ['Virtual stops',       String(data?.total_virtual_stops||0)],
            ['Tracking events',     String(data?.total_tracking_events||0)],
          ].map(([l,v]) => (
            <div key={l} style={s({ display:'flex', justifyContent:'space-between', padding:'7px 0', borderBottom:`1px solid ${C.border}` })}>
              <p style={s({ color:C.muted2, fontSize:12 })}>{l}</p>
              <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>{v}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={s({ display:'flex', gap:10, flexWrap:'wrap' })}>
        {(['admin-rides','admin-vehicles','admin-cluster','admin-routes','admin-analytics','admin-jobs','admin-heatmap'] as const).map(v => (
          <button key={v} onClick={()=>setView(v)} style={s({ padding:'10px 18px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.text, borderRadius:9, fontSize:12, fontWeight:600, cursor:'pointer' })}>
            {v.replace('admin-','').charAt(0).toUpperCase()+v.replace('admin-','').slice(1)} →
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── Rides Panel ──────────────────────────────────────────────────────────────
function RidesPanel({ setView, toast }: any) {
  const [rides,   setRides]   = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState('')

  const load = useCallback(async () => {
    try { const r = await ridesApi.getAll({ limit:50 }); setRides(Array.isArray(r)?r:[]) }
    catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])
  useEffect(() => { load() }, [load])

  const updateStatus = async (id:number, status:string) => {
    try { await ridesApi.updateStatus(id, status); setRides(p => p.map(r => r.id===id?{...r,status}:r)); toast('success',`Ride #${id} → ${status}`) }
    catch(e:any) { toast('error','Failed', e?.response?.data?.detail||'') }
  }

  const filtered = filter ? rides.filter(r => r.status===filter) : rides

  return (
    <div style={s({ padding:28 })}>
      <PageHeader title="All Rides" back="Overview" onBack={()=>setView('admin-overview')} />
      <div style={s({ display:'flex', gap:8, marginBottom:16, flexWrap:'wrap' })}>
        {['','pending','clustered','assigned','in_progress','completed','cancelled'].map(st => (
          <button key={st} onClick={()=>setFilter(st)} style={s({ padding:'6px 12px', borderRadius:7, border:`1px solid ${filter===st?C.accent:C.border}`, background:filter===st?`${C.accent}18`:'transparent', color:filter===st?C.accent:C.muted2, fontSize:11, fontWeight:600, cursor:'pointer' })}>
            {st||'All'}
          </button>
        ))}
        <button onClick={load} style={s({ marginLeft:'auto', padding:'6px 12px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.muted2, fontSize:11, borderRadius:7, cursor:'pointer' })}>↻ Refresh</button>
      </div>
      {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
      <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
        {filtered.map(r => (
          <div key={r.id} style={s({ padding:'12px 16px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:10 })}>
            <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:6 })}>
              <div>
                <span style={s({ color:C.muted, fontSize:11, marginRight:8 })}>#{r.id}</span>
                <Badge val={r.status} />
              </div>
              <p style={s({ color:C.muted, fontSize:11 })}>{r.request_time ? new Date(r.request_time).toLocaleString() : ''}</p>
            </div>
            <p style={s({ color:C.text, fontSize:12, marginBottom:2 })}>📍 {r.pickup_label||`${r.pickup_lat?.toFixed(3)},${r.pickup_lng?.toFixed(3)}`}</p>
            <p style={s({ color:C.text, fontSize:12, marginBottom:8 })}>🎯 {r.destination_label||`${r.dest_lat?.toFixed(3)},${r.dest_lng?.toFixed(3)}`}</p>
            <div style={s({ display:'flex', gap:6, flexWrap:'wrap' })}>
              {r.status==='pending'     && <Btn small label="Cluster →"    onClick={()=>updateStatus(r.id,'clustered')} />}
              {r.status==='clustered'   && <Btn small label="Assign →"     onClick={()=>updateStatus(r.id,'assigned')} />}
              {r.status==='assigned'    && <Btn small label="Start →"      onClick={()=>updateStatus(r.id,'in_progress')} />}
              {r.status==='in_progress' && <Btn small label="Complete ✓"   onClick={()=>updateStatus(r.id,'completed')} color="#22c55e" />}
              {!['completed','cancelled'].includes(r.status) && <Btn small label="Cancel" onClick={()=>updateStatus(r.id,'cancelled')} color={C.danger} />}
            </div>
          </div>
        ))}
        {!loading && filtered.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No rides found.</p>}
      </div>
    </div>
  )
}

// ─── Vehicles Panel ───────────────────────────────────────────────────────────
function VehiclesPanel({ setView, toast }: any) {
  const [vehicles, setVehicles] = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ license_plate:'', capacity:'4', lat:'12.9784', lng:'77.6408' })

  const load = useCallback(async () => {
    try { const v = await vehiclesApi.list(); setVehicles(Array.isArray(v)?v:[]) }
    catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])
  useEffect(() => { load() }, [load])

  const create = async () => {
    if (!form.license_plate.trim()) { toast('warning','Enter a license plate'); return }
    setCreating(true)
    try {
      await vehiclesApi.create({ license_plate:form.license_plate, capacity:Number(form.capacity), lat:Number(form.lat), lng:Number(form.lng) })
      toast('success','Vehicle created')
      setForm({ license_plate:'', capacity:'4', lat:'12.9784', lng:'77.6408' })
      load()
    } catch(e:any) { toast('error','Failed', e?.response?.data?.detail||'') }
    setCreating(false)
  }

  const updateStatus = async (id:number, status:string) => {
    try { await vehiclesApi.update(id, { status }); setVehicles(p => p.map(v => v.id===id?{...v,status}:v)); toast('success',`Vehicle #${id} → ${status}`) }
    catch(e:any) { toast('error','Failed', e?.response?.data?.detail||'') }
  }

  return (
    <div style={s({ padding:28 })}>
      <PageHeader title="Fleet Management" back="Overview" onBack={()=>setView('admin-overview')} />
      <div style={s({ display:'flex', gap:20, flexWrap:'wrap' })}>
        {/* Create form */}
        <div style={s({ flex:'0 0 280px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, height:'fit-content' })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:14 })}>Add Vehicle</p>
          {[
            { label:'License Plate', key:'license_plate', ph:'KA01AB1234' },
            { label:'Capacity',      key:'capacity',      ph:'4' },
            { label:'Lat',           key:'lat',           ph:'12.9784' },
            { label:'Lng',           key:'lng',           ph:'77.6408' },
          ].map(f => (
            <div key={f.key} style={s({ marginBottom:10 })}>
              <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:5 })}>{f.label}</label>
              <input value={(form as any)[f.key]} onChange={e=>setForm(p=>({...p,[f.key]:e.target.value}))} placeholder={f.ph}
                style={s({ width:'100%', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, color:C.text, fontSize:13, outline:'none' })} />
            </div>
          ))}
          <button onClick={create} disabled={creating} style={s({ width:'100%', padding:'10px', background:C.accent, color:C.bg, border:'none', borderRadius:8, fontSize:13, fontWeight:700, cursor:'pointer', marginTop:4 })}>
            {creating ? 'Creating…' : '+ Add Vehicle'}
          </button>
        </div>

        {/* Vehicle list */}
        <div style={s({ flex:'1 1 340px' })}>
          <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Vehicles ({vehicles.length})</p>
            <button onClick={load} style={s({ background:'none', border:'none', color:C.accent, fontSize:12, cursor:'pointer' })}>↻ Refresh</button>
          </div>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {vehicles.map(v => (
              <div key={v.id} style={s({ padding:'12px 14px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:10 })}>
                <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 })}>
                  <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>{v.license_plate} <span style={s({ color:C.muted, fontSize:11 })}>· cap {v.capacity}</span></p>
                  <Badge val={v.status} />
                </div>
                {v.lat && <p style={s({ color:C.muted, fontSize:11, marginBottom:8 })}>GPS: {v.lat?.toFixed(4)}, {v.lng?.toFixed(4)}</p>}
                {v.assigned_route_id && <p style={s({ color:C.muted2, fontSize:11, marginBottom:8, fontFamily:'monospace' })}>Route: {v.assigned_route_id.slice(0,24)}</p>}
                <div style={s({ display:'flex', gap:6 })}>
                  {v.status!=='idle'    && <Btn small label="Set Idle"   onClick={()=>updateStatus(v.id,'idle')}    color={C.muted2} />}
                  {v.status!=='active'  && <Btn small label="Set Active" onClick={()=>updateStatus(v.id,'active')}  />}
                  {v.status!=='offline' && <Btn small label="Offline"    onClick={()=>updateStatus(v.id,'offline')} color={C.danger} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Cluster Panel ────────────────────────────────────────────────────────────
function ClusterPanel({ setView, toast }: any) {
  const [history,  setHistory]  = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [minSize,  setMinSize]  = useState('2')
  const [resolution, setRes]   = useState('9')

  const load = useCallback(async () => {
    try { const h = await clusterApi.history(); setHistory(h?.runs||[]) }
    catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])
  useEffect(() => { load() }, [load])

  const runCluster = async () => {
    setRunning(true)
    try {
      const res = await clusterApi.run({ resolution:Number(resolution), min_cluster_size:Number(minSize) })
      toast('success',`Clustering done — ${res.clusters_formed} clusters, ${res.total_processed_requests} rides`)
      load()
    } catch(e:any) { toast('error','Clustering failed', e?.response?.data?.detail||'') }
    setRunning(false)
  }

  return (
    <div style={s({ padding:28 })}>
      <PageHeader title="Demand Clustering" back="Overview" onBack={()=>setView('admin-overview')} />
      <div style={s({ display:'flex', gap:20, flexWrap:'wrap' })}>
        {/* Run controls */}
        <div style={s({ flex:'0 0 260px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, height:'fit-content' })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:14 })}>Run HDBSCAN Clustering</p>
          <div style={s({ marginBottom:12 })}>
            <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:5 })}>H3 Resolution</label>
            <input value={resolution} onChange={e=>setRes(e.target.value)} type="number" min="7" max="12"
              style={s({ width:'100%', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, color:C.text, fontSize:13, outline:'none' })} />
          </div>
          <div style={s({ marginBottom:14 })}>
            <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:5 })}>Min Cluster Size</label>
            <input value={minSize} onChange={e=>setMinSize(e.target.value)} type="number" min="2"
              style={s({ width:'100%', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, color:C.text, fontSize:13, outline:'none' })} />
          </div>
          <button onClick={runCluster} disabled={running} style={s({ width:'100%', padding:'10px', background:C.accent3, color:C.bg, border:'none', borderRadius:8, fontSize:13, fontWeight:700, cursor:running?'not-allowed':'pointer', opacity:running?0.6:1 })}>
            {running ? '⏳ Running…' : '🔬 Run Clustering'}
          </button>
          <p style={s({ color:C.muted, fontSize:11, marginTop:10, lineHeight:1.6 })}>Clusters pending rides by H3 cell using HDBSCAN, then snaps centroids to nearest road node.</p>
        </div>

        {/* History */}
        <div style={s({ flex:'1 1 340px' })}>
          <div style={s({ display:'flex', justifyContent:'space-between', marginBottom:12 })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Cluster Run History</p>
            <button onClick={load} style={s({ background:'none', border:'none', color:C.accent, fontSize:12, cursor:'pointer' })}>↻ Refresh</button>
          </div>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {history.map(run => (
              <div key={run.id} onClick={()=>setSelected(selected?.id===run.id?null:run)} style={s({ padding:'12px 14px', background:C.surface, border:`1px solid ${selected?.id===run.id?C.accent3:C.border}`, borderRadius:10, cursor:'pointer' })}>
                <div style={s({ display:'flex', justifyContent:'space-between', marginBottom:6 })}>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>Run #{run.id}</p>
                  <Badge val={run.status} />
                </div>
                <div style={s({ display:'flex', gap:16 })}>
                  <p style={s({ color:C.muted2, fontSize:11 })}>📦 {run.total_processed_requests} rides</p>
                  <p style={s({ color:C.muted2, fontSize:11 })}>🔵 {run.clusters_formed} clusters</p>
                  <p style={s({ color:C.muted2, fontSize:11 })}>🔇 {run.noise_requests_count} noise</p>
                </div>
                <p style={s({ color:C.muted, fontSize:11, marginTop:4 })}>{run.created_at ? new Date(run.created_at).toLocaleString() : ''}</p>
                {selected?.id===run.id && run.cluster_summary?.length > 0 && (
                  <div style={s({ marginTop:10, borderTop:`1px solid ${C.border}`, paddingTop:10 })}>
                    <p style={s({ color:C.muted2, fontSize:11, fontWeight:700, marginBottom:6 })}>Cluster Summary</p>
                    {run.cluster_summary.slice(0,5).map((cs:any) => (
                      <div key={cs.cluster_id} style={s({ padding:'6px 8px', background:C.surface2, borderRadius:6, marginBottom:4 })}>
                        <p style={s({ color:C.text, fontSize:11 })}>Cluster #{cs.cluster_id} · {cs.passenger_count} passengers</p>
                        <p style={s({ color:C.muted, fontSize:10 })}>Stop: {cs.virtual_stop_lat?.toFixed(4)}, {cs.virtual_stop_lng?.toFixed(4)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {!loading && history.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No cluster runs yet.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Routes Panel ─────────────────────────────────────────────────────────────
function RoutesPanel({ setView, toast }: any) {
  const [routes,   setRoutes]   = useState<any[]>([])
  const [vehicles, setVehicles] = useState<any[]>([])
  const [clusters, setClusters] = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [depotLat, setDepotLat] = useState('12.9784')
  const [depotLng, setDepotLng] = useState('77.6408')

  const load = useCallback(async () => {
    try {
      const [ro, ve, cl] = await Promise.all([routeApi.history(), vehiclesApi.idle(), clusterApi.history(5)])
      setRoutes(ro?.routes||[])
      setVehicles(Array.isArray(ve)?ve:[])
      setClusters(cl?.runs||[])
    } catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])
  useEffect(() => { load() }, [load])

  const runOptimize = async () => {
    if (vehicles.length===0) { toast('warning','No idle vehicles available'); return }
    const latestCluster = clusters[0]
    if (!latestCluster?.cluster_summary?.length) { toast('warning','No cluster summary available — run clustering first'); return }
    const stopIds = latestCluster.cluster_summary.map((c:any) => c.virtual_stop_id).filter(Boolean)
    if (!stopIds.length) { toast('warning','No virtual stops in latest cluster'); return }
    setRunning(true)
    try {
      const res = await routeApi.optimize({
        vehicle_ids: vehicles.slice(0,3).map((v:any)=>v.id),
        virtual_stop_ids: stopIds,
        depot_lat: Number(depotLat),
        depot_lng: Number(depotLng),
        source_cluster_run_id: latestCluster.id,
      })
      toast('success',`Routes optimized — ${res.routes?.length||0} routes`, `${res.unassigned_stops?.length||0} unassigned stops`)
      load()
    } catch(e:any) { toast('error','Optimization failed', e?.response?.data?.detail||'') }
    setRunning(false)
  }

  return (
    <div style={s({ padding:28 })}>
      <PageHeader title="Route Optimization" back="Overview" onBack={()=>setView('admin-overview')} />
      <div style={s({ display:'flex', gap:20, flexWrap:'wrap' })}>
        {/* Controls */}
        <div style={s({ flex:'0 0 260px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, height:'fit-content' })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:14 })}>Run VRP Optimization</p>
          <div style={s({ marginBottom:10 })}>
            <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:5 })}>Depot Lat</label>
            <input value={depotLat} onChange={e=>setDepotLat(e.target.value)} style={s({ width:'100%', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, color:C.text, fontSize:13, outline:'none' })} />
          </div>
          <div style={s({ marginBottom:14 })}>
            <label style={s({ display:'block', color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:5 })}>Depot Lng</label>
            <input value={depotLng} onChange={e=>setDepotLng(e.target.value)} style={s({ width:'100%', padding:'9px 11px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:8, color:C.text, fontSize:13, outline:'none' })} />
          </div>
          <div style={s({ padding:'10px 12px', background:C.surface2, borderRadius:8, marginBottom:14 })}>
            <p style={s({ color:C.muted2, fontSize:11 })}>Idle vehicles: <span style={s({ color:C.text, fontWeight:700 })}>{vehicles.length}</span></p>
            <p style={s({ color:C.muted2, fontSize:11, marginTop:3 })}>Latest cluster: <span style={s({ color:C.text, fontWeight:700 })}>{clusters[0] ? `#${clusters[0].id} (${clusters[0].clusters_formed} clusters)` : '—'}</span></p>
          </div>
          <button onClick={runOptimize} disabled={running} style={s({ width:'100%', padding:'10px', background:C.accent2, color:C.bg, border:'none', borderRadius:8, fontSize:13, fontWeight:700, cursor:running?'not-allowed':'pointer', opacity:running?0.6:1 })}>
            {running ? '⏳ Optimizing…' : '📍 Optimize Routes'}
          </button>
          <p style={s({ color:C.muted, fontSize:11, marginTop:10, lineHeight:1.6 })}>Uses OR-Tools CVRP solver with Hungarian assignment to optimally dispatch idle vehicles.</p>
        </div>

        {/* Route history */}
        <div style={s({ flex:'1 1 340px' })}>
          <div style={s({ display:'flex', justifyContent:'space-between', marginBottom:12 })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Route History</p>
            <button onClick={load} style={s({ background:'none', border:'none', color:C.accent, fontSize:12, cursor:'pointer' })}>↻ Refresh</button>
          </div>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:8 })}>
            {routes.map(r => (
              <div key={r.id} onClick={()=>setSelected(selected?.id===r.id?null:r)} style={s({ padding:'12px 14px', background:C.surface, border:`1px solid ${selected?.id===r.id?C.accent2:C.border}`, borderRadius:10, cursor:'pointer' })}>
                <div style={s({ display:'flex', justifyContent:'space-between', marginBottom:4 })}>
                  <p style={s({ color:C.text, fontSize:11, fontWeight:700, fontFamily:'monospace' })}>{r.route_id?.slice(0,24)}</p>
                  <Badge val={r.status} />
                </div>
                <p style={s({ color:C.muted2, fontSize:11 })}>Vehicle #{r.vehicle_id} · {r.total_distance_meters ? `${(r.total_distance_meters/1000).toFixed(2)} km` : '—'} · {r.waypoints?.length||0} stops</p>
                <p style={s({ color:C.muted, fontSize:11, marginTop:2 })}>{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</p>
                {selected?.id===r.id && (
                  <div style={s({ marginTop:10, borderTop:`1px solid ${C.border}`, paddingTop:10 })}>
                    {/* Route map */}
                    {r.waypoints?.length > 0 && (
                      <AppMap
                        center={[r.waypoints[0].lat, r.waypoints[0].lng]}
                        zoom={13}
                        height={200}
                        waypoints={r.waypoints}
                        style={{ marginBottom:10 }}
                      />
                    )}
                    {(r.waypoints||[]).map((wp:any,i:number) => (
                      <div key={i} style={s({ display:'flex', alignItems:'center', gap:8, padding:'5px 0', borderBottom:`1px solid ${C.border}` })}>
                        <span style={s({ color:C.muted, fontSize:10, width:16, textAlign:'center' })}>{i+1}</span>
                        <span style={s({ fontSize:10, textTransform:'uppercase', color:wp.waypoint_type==='depot'?C.muted:C.accent, fontWeight:700 })}>{wp.waypoint_type}</span>
                        <span style={s({ color:C.muted2, fontSize:10 })}>{wp.lat?.toFixed(4)}, {wp.lng?.toFixed(4)}</span>
                        {wp.passenger_ids?.length>0 && <span style={s({ marginLeft:'auto', color:C.muted, fontSize:10 })}>👤{wp.passenger_ids.length}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {!loading && routes.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No routes yet. Run clustering first, then optimize.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Analytics Panel ──────────────────────────────────────────────────────────
function AnalyticsPanel({ setView, toast }: any) {
  const [overview, setOverview] = useState<any>(null)
  const [daily,    setDaily]    = useState<any[]>([])
  const [days,     setDays]     = useState(14)
  const [loading,  setLoading]  = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, da] = await Promise.all([analyticsApi.overview(), analyticsApi.daily(days)])
      setOverview(ov)
      setDaily(da?.points||[])
    } catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [days, toast])
  useEffect(() => { load() }, [load])

  const maxRides = Math.max(1, ...daily.map((d:any) => d.ride_requests))
  return (
    <div style={s({ padding:28, maxWidth:900 })}>
      <PageHeader title="Analytics" back="Overview" onBack={()=>setView('admin-overview')} />
      {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
      {!loading && overview && (
        <>
          <div style={s({ display:'flex', gap:12, flexWrap:'wrap', marginBottom:24 })}>
            <StatCard label="Total Rides"  val={overview.total_rides}  icon="🛻" col={C.accent} />
            <StatCard label="Completed"    val={overview.rides_by_status?.completed||0}  icon="✅" col="#22c55e" />
            <StatCard label="Pending"      val={overview.rides_by_status?.pending||0}    icon="⏳" col={C.accent2} />
            <StatCard label="Utilisation"  val={`${overview.route_utilization_percent}%`} icon="📊" col={C.accent3} />
          </div>

          {/* Bar chart */}
          <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:20, marginBottom:20 })}>
            <div style={s({ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 })}>
              <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Daily Ride Requests</p>
              <div style={s({ display:'flex', gap:6 })}>
                {[7,14,30].map(d => (
                  <button key={d} onClick={()=>setDays(d)} style={s({ padding:'4px 10px', borderRadius:6, border:`1px solid ${days===d?C.accent:C.border}`, background:days===d?`${C.accent}18`:'transparent', color:days===d?C.accent:C.muted2, fontSize:11, cursor:'pointer' })}>{d}d</button>
                ))}
              </div>
            </div>
            <div style={s({ display:'flex', alignItems:'flex-end', gap:4, height:120, padding:'0 4px' })}>
              {daily.map((d:any) => {
                const h = Math.max(4, (d.ride_requests/maxRides)*110)
                const date = new Date(d.day).toLocaleDateString('en',{month:'short',day:'numeric'})
                return (
                  <div key={d.day} style={s({ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:4 })}>
                    <div title={`${d.ride_requests} rides`} style={s({ width:'100%', height:h, background:`${C.accent}cc`, borderRadius:'3px 3px 0 0', minWidth:4, transition:'height 0.3s' })} />
                    {daily.length <= 14 && <p style={s({ color:C.muted, fontSize:9, transform:'rotate(-30deg)', whiteSpace:'nowrap', transformOrigin:'top center' })}>{date}</p>}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Daily table */}
          <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden' })}>
            <div style={s({ display:'grid', gridTemplateColumns:'1fr 80px 80px 80px 80px 80px', padding:'9px 16px', background:C.surface2, borderBottom:`1px solid ${C.border}` })}>
              {['Date','Requests','Clustered','Completed','Cancelled','Routes'].map(h => (
                <p key={h} style={s({ color:C.muted2, fontSize:11, fontWeight:700 })}>{h}</p>
              ))}
            </div>
            {daily.slice().reverse().map((d:any) => (
              <div key={d.day} style={s({ display:'grid', gridTemplateColumns:'1fr 80px 80px 80px 80px 80px', padding:'9px 16px', borderBottom:`1px solid ${C.border}` })}>
                <p style={s({ color:C.text, fontSize:12 })}>{new Date(d.day).toLocaleDateString('en',{month:'short',day:'numeric',year:'2-digit'})}</p>
                <p style={s({ color:C.text, fontSize:12, fontWeight:700 })}>{d.ride_requests}</p>
                <p style={s({ color:'#a78bfa', fontSize:12 })}>{d.clustered_rides}</p>
                <p style={s({ color:'#22c55e', fontSize:12 })}>{d.completed_rides}</p>
                <p style={s({ color:C.danger,  fontSize:12 })}>{d.cancelled_rides}</p>
                <p style={s({ color:C.accent2, fontSize:12 })}>{d.route_plans}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Jobs Panel ───────────────────────────────────────────────────────────────
function JobsPanel({ setView, toast }: any) {
  const [status,   setStatus]   = useState<any>(null)
  const [runs,     setRuns]     = useState<any[]>([])
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState<string|null>(null)

  const load = useCallback(async () => {
    try {
      const [st, ru, sg] = await Promise.all([jobsApi.status(), jobsApi.runs(), jobsApi.rebalanceSuggestions()])
      setStatus(st); setRuns(ru||[]); setSuggestions(sg||[])
    } catch(e:any) { toast('error','Failed',e?.response?.data?.detail||'') }
    setLoading(false)
  }, [toast])
  useEffect(() => { load() }, [load])

  const runJob = async (type: 'clustering'|'demand'|'rebalance') => {
    setRunning(type)
    try {
      const fn = type==='clustering' ? jobsApi.runClustering : type==='demand' ? jobsApi.runDemand : jobsApi.runRebalance
      const res = await fn()
      toast('success', `${type} job triggered`, res?.message||'')
      setTimeout(load, 1500)
    } catch(e:any) { toast('error','Job failed', e?.response?.data?.detail||'') }
    setRunning(null)
  }

  return (
    <div style={s({ padding:28, maxWidth:900 })}>
      <PageHeader title="Background Jobs" back="Overview" onBack={()=>setView('admin-overview')} />

      {/* Job status */}
      {status && (
        <div style={s({ display:'flex', gap:12, flexWrap:'wrap', marginBottom:24 })}>
          <div style={s({ flex:'1 1 200px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:'16px 18px' })}>
            <p style={s({ color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:8 })}>Scheduler</p>
            <span style={s({ fontSize:11, fontWeight:700, color:status.scheduler_running?C.accent:C.danger, background:(status.scheduler_running?C.accent:C.danger)+'22', padding:'3px 9px', borderRadius:6 })}>{status.scheduler_running?'RUNNING':'STOPPED'}</span>
          </div>
          {[
            { label:'Cluster Interval', val:`${status.cluster_interval_seconds}s`, last:status.last_cluster_run_at },
            { label:'Demand Interval',  val:`${status.demand_interval_seconds}s`,  last:status.last_demand_run_at },
            { label:'Rebalance Interval',val:`${status.rebalance_interval_seconds}s`,last:status.last_rebalance_run_at },
          ].map(item => (
            <div key={item.label} style={s({ flex:'1 1 180px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:'16px 18px' })}>
              <p style={s({ color:C.muted2, fontSize:11, fontWeight:700, textTransform:'uppercase', marginBottom:6 })}>{item.label}</p>
              <p style={s({ color:C.text, fontSize:16, fontWeight:800 })}>{item.val}</p>
              <p style={s({ color:C.muted, fontSize:10, marginTop:4 })}>Last: {item.last ? new Date(item.last).toLocaleTimeString() : '—'}</p>
            </div>
          ))}
        </div>
      )}

      {/* Manual triggers */}
      <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:20, marginBottom:20 })}>
        <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:14 })}>Manual Triggers</p>
        <div style={s({ display:'flex', gap:10, flexWrap:'wrap' })}>
          {([
            { key:'clustering', label:'🔬 Run Clustering',  col:C.accent3 },
            { key:'demand',     label:'📊 Refresh Demand',  col:'#60a5fa' },
            { key:'rebalance',  label:'🚗 Rebalance Fleet', col:C.accent2 },
          ] as const).map(j => (
            <button key={j.key} onClick={()=>runJob(j.key)} disabled={!!running} style={s({ padding:'10px 18px', background:`${j.col}22`, border:`1px solid ${j.col}55`, color:j.col, fontSize:12, fontWeight:700, borderRadius:8, cursor:running?'not-allowed':'pointer', opacity:running?0.6:1 })}>
              {running===j.key ? '⏳ Running…' : j.label}
            </button>
          ))}
          <button onClick={load} style={s({ padding:'10px 14px', background:C.surface2, border:`1px solid ${C.border2}`, color:C.muted2, fontSize:12, borderRadius:8, cursor:'pointer', marginLeft:'auto' })}>↻ Refresh</button>
        </div>
      </div>

      <div style={s({ display:'flex', gap:16, flexWrap:'wrap' })}>
        {/* Job run history */}
        <div style={s({ flex:'1 1 340px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:12 })}>Recent Job Runs</p>
          {loading && <p style={s({ color:C.muted, fontSize:13 })}>Loading…</p>}
          <div style={s({ display:'flex', flexDirection:'column', gap:6 })}>
            {runs.slice(0,15).map((r:any) => (
              <div key={r.id} style={s({ padding:'9px 12px', background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8 })}>
                <div style={s({ display:'flex', justifyContent:'space-between', marginBottom:3 })}>
                  <p style={s({ color:C.text, fontSize:12, fontWeight:600 })}>{r.job_type?.replace(/_/g,' ')}</p>
                  <Badge val={r.status} />
                </div>
                <p style={s({ color:C.muted, fontSize:10 })}>{r.started_at ? new Date(r.started_at).toLocaleString() : ''}{r.duration_seconds ? ` · ${r.duration_seconds.toFixed(1)}s` : ''}</p>
                {r.error_message && <p style={s({ color:C.danger, fontSize:10, marginTop:2 })}>{r.error_message}</p>}
              </div>
            ))}
            {!loading && runs.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No runs yet.</p>}
          </div>
        </div>

        {/* Rebalance suggestions */}
        <div style={s({ flex:'1 1 280px', background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18 })}>
          <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:12 })}>Rebalance Suggestions</p>
          <div style={s({ display:'flex', flexDirection:'column', gap:6 })}>
            {suggestions.slice(0,10).map((sg:any) => (
              <div key={sg.id} style={s({ padding:'9px 12px', background:C.surface2, borderRadius:8 })}>
                <p style={s({ color:C.text, fontSize:12, fontWeight:600 })}>Vehicle #{sg.vehicle_id}</p>
                <p style={s({ color:C.muted2, fontSize:11 })}>→ {sg.target_lat?.toFixed(4)}, {sg.target_lng?.toFixed(4)}</p>
                <p style={s({ color:C.muted, fontSize:10 })}>{sg.reason} · {sg.created_at ? new Date(sg.created_at).toLocaleString() : ''}</p>
              </div>
            ))}
            {!loading && suggestions.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No suggestions yet.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Heatmap Panel ────────────────────────────────────────────────────────────
function HeatmapPanel({ setView, toast }: any) {
  const [cells,    setCells]    = useState<any[]>([])
  const [loading,  setLoading]  = useState(false)
  const [minLat,   setMinLat]   = useState('12.80')
  const [maxLat,   setMaxLat]   = useState('13.10')
  const [minLng,   setMinLng]   = useState('77.40')
  const [maxLng,   setMaxLng]   = useState('77.80')

  const load = async () => {    setLoading(true)
    try {
      const res = await predictApi.heatmap({
        min_lat:Number(minLat), max_lat:Number(maxLat),
        min_lng:Number(minLng), max_lng:Number(maxLng),
      })
      setCells(res?.cells||[])
      if ((res?.cells||[]).length===0) toast('info','No demand data','No rides in this area/timeframe')
    } catch(e:any) { toast('error','Failed', e?.response?.data?.detail||'') }
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const maxDemand = Math.max(1, ...cells.map((c:any) => c.predicted_demand||c.historical_request_count||0))

  return (
    <div style={s({ padding:28, maxWidth:900 })}>
      <PageHeader title="Demand Heatmap" back="Overview" onBack={()=>setView('admin-overview')} />

      {/* Controls */}
      <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:18, marginBottom:20 })}>
        <p style={s({ color:C.text, fontSize:13, fontWeight:700, marginBottom:12 })}>Bounding Box (Bengaluru)</p>
        <div style={s({ display:'flex', gap:10, flexWrap:'wrap', marginBottom:12 })}>
          {[
            { label:'Min Lat', val:minLat, set:setMinLat },
            { label:'Max Lat', val:maxLat, set:setMaxLat },
            { label:'Min Lng', val:minLng, set:setMinLng },
            { label:'Max Lng', val:maxLng, set:setMaxLng },
          ].map(f => (
            <div key={f.label} style={s({ flex:'1 1 120px' })}>
              <label style={s({ display:'block', color:C.muted2, fontSize:10, fontWeight:700, textTransform:'uppercase', marginBottom:4 })}>{f.label}</label>
              <input value={f.val} onChange={e=>f.set(e.target.value)} style={s({ width:'100%', padding:'8px 10px', background:C.surface2, border:`1px solid ${C.border2}`, borderRadius:7, color:C.text, fontSize:13, outline:'none' })} />
            </div>
          ))}
        </div>
        <button onClick={load} disabled={loading} style={s({ padding:'9px 18px', background:C.danger, color:'#fff', border:'none', borderRadius:8, fontSize:12, fontWeight:700, cursor:loading?'not-allowed':'pointer', opacity:loading?0.6:1 })}>
          {loading ? '⏳ Loading…' : '🔥 Fetch Heatmap'}
        </button>
      </div>

      {/* Heatmap — map + table */}
      {cells.length > 0 && (
        <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden', marginBottom:20 })}>
          <div style={s({ padding:'12px 18px', borderBottom:`1px solid ${C.border}` })}>
            <p style={s({ color:C.text, fontSize:13, fontWeight:700 })}>Demand Map — {cells.length} H3 cells</p>
            <p style={s({ color:C.muted2, fontSize:11, marginTop:2 })}>Darker red = higher predicted demand · hover for details</p>
          </div>
          {/* Real Leaflet map with heat circles */}
          <AppMap
            center={[
              (Number(minLat)+Number(maxLat))/2,
              (Number(minLng)+Number(maxLng))/2,
            ]}
            zoom={12}
            height={380}
            heatCells={cells}
          />
        </div>
      )}

      {/* Cells table */}
      {cells.length > 0 && (
        <div style={s({ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden' })}>
          <div style={s({ display:'grid', gridTemplateColumns:'2fr 80px 80px 80px 80px', padding:'9px 16px', background:C.surface2, borderBottom:`1px solid ${C.border}` })}>
            {['H3 Index','Lat','Lng','Historic','Predicted'].map(h => (
              <p key={h} style={s({ color:C.muted2, fontSize:11, fontWeight:700 })}>{h}</p>
            ))}
          </div>
          <div style={s({ maxHeight:320, overflowY:'auto' })}>
            {cells.sort((a:any,b:any)=>(b.predicted_demand||0)-(a.predicted_demand||0)).map((c:any) => (
              <div key={c.h3_index} style={s({ display:'grid', gridTemplateColumns:'2fr 80px 80px 80px 80px', padding:'8px 16px', borderBottom:`1px solid ${C.border}` })}>
                <p style={s({ color:C.text, fontSize:11, fontFamily:'monospace' })}>{c.h3_index}</p>
                <p style={s({ color:C.muted2, fontSize:11 })}>{c.latitude?.toFixed(3)}</p>
                <p style={s({ color:C.muted2, fontSize:11 })}>{c.longitude?.toFixed(3)}</p>
                <p style={s({ color:C.text,   fontSize:11, fontWeight:700 })}>{c.historical_request_count}</p>
                <p style={s({ color:C.danger, fontSize:11, fontWeight:700 })}>{c.predicted_demand?.toFixed(1)||'—'}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {!loading && cells.length===0 && <p style={s({ color:C.muted, fontSize:13 })}>No demand data found. Book some rides first to generate data.</p>}
    </div>
  )
}
