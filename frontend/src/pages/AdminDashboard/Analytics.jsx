import React, { useEffect, useState } from 'react';
import { Box, Grid, Typography, Alert } from '@mui/material';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { analyticsApi } from '../../services/api';

export const Analytics = () => {
  const [overview, setOverview] = useState({}); const [daily, setDaily] = useState([]); const [error, setError] = useState('');
  useEffect(() => { Promise.all([analyticsApi.getOverview(), analyticsApi.getDaily()]).then(([o, d]) => { setOverview(o); setDaily(d.days || d.daily || []); }).catch((e) => setError(e.response?.data?.detail || 'Unable to load analytics.')); }, []);
  return <DashboardLayout title="AI Route Optimization & Analytics"><Grid container spacing={3}>{error && <Grid item xs={12}><Alert severity="error">{error}</Alert></Grid>}<Grid item xs={12} md={4}><GlassCard sx={{ p: 3 }}><Typography variant="caption">TOTAL RIDES</Typography><Typography variant="h3" sx={{ fontWeight: 800, color: '#00D4FF' }}>{overview.total_rides || 0}</Typography></GlassCard></Grid><Grid item xs={12} md={4}><GlassCard sx={{ p: 3 }}><Typography variant="caption">ACTIVE VEHICLES</Typography><Typography variant="h3" sx={{ fontWeight: 800 }}>{overview.active_vehicles || 0}</Typography></GlassCard></Grid><Grid item xs={12} md={4}><GlassCard sx={{ p: 3 }}><Typography variant="caption">TRACKING EVENTS</Typography><Typography variant="h3" sx={{ fontWeight: 800, color: '#10B981' }}>{overview.total_tracking_events || 0}</Typography></GlassCard></Grid><Grid item xs={12}><GlassCard sx={{ p: 3 }}><Typography variant="h6" sx={{ fontWeight: 800, mb: 2 }}>Daily backend activity</Typography>{daily.length ? daily.map((d) => <Box key={d.date} sx={{ display: 'flex', justifyContent: 'space-between', py: 1, borderBottom: '1px solid rgba(255,255,255,.08)' }}><Typography>{d.date}</Typography><Typography>{d.ride_count ?? d.rides ?? 0} rides</Typography></Box>) : <Typography color="text.secondary">No daily analytics available yet.</Typography>}</GlassCard></Grid></Grid></DashboardLayout>;
};
