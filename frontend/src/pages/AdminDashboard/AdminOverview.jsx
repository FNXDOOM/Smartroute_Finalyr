import React, { useState } from 'react';
import { Box, Grid, Typography, Card, Chip, Stack, Alert } from '@mui/material';
import { Car, Users, DollarSign, Leaf, Zap, Activity, Cpu, ArrowUpRight } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { InteractiveMap } from '../../components/maps/InteractiveMap';
import { MOCK_ADMIN_METRICS, MOCK_DEMAND_HEATMAP_CELLS } from '../../services/mockData';

export const AdminOverview = () => {
  const [heatmapEnabled, setHeatmapEnabled] = useState(true);

  return (
    <DashboardLayout title="Admin Control Center">
      {/* Overview Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>TOTAL SYSTEM RIDES</Typography>
              <Car size={20} color="#00D4FF" />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#00D4FF' }}>{MOCK_ADMIN_METRICS.totalRides.toLocaleString()}</Typography>
            <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>+14% vs last week</Typography>
          </GlassCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>ACTIVE EV FLEET</Typography>
              <Activity size={20} color="#10B981" />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800 }}>{MOCK_ADMIN_METRICS.activeDrivers} Vehicles</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>84.6% Fleet Utilization</Typography>
          </GlassCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>ACTIVE RIDERS</Typography>
              <Users size={20} color="#1E88E5" />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800 }}>{MOCK_ADMIN_METRICS.activeRiders.toLocaleString()}</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Online on App</Typography>
          </GlassCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>TOTAL REVENUE TODAY</Typography>
              <DollarSign size={20} color="#F59E0B" />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#10B981' }}>₹ 1,84,500</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Flat-fare guaranteed</Typography>
          </GlassCard>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Left AI Insights & Predictive Demand Panel */}
        <Grid item xs={12} md={4}>
          <GlassCard sx={{ p: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <Cpu size={22} color="#00D4FF" />
              <Typography variant="h6" sx={{ fontWeight: 800, color: '#00D4FF' }}>
                AI Demand Insights
              </Typography>
            </Box>

            <Stack spacing={2}>
              <Card sx={{ p: 2, background: 'rgba(0, 212, 255, 0.08)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 3 }}>
                <Chip label="PREDICTIVE HEATMAP ALERT" color="primary" size="small" sx={{ fontWeight: 800, mb: 1 }} />
                <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  Outer Ring Road Zone #4 Peak Demand
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  Demand expected to rise +28% between 6:00 PM - 7:30 PM. 18 EV vehicles pre-positioned automatically.
                </Typography>
              </Card>

              <Card sx={{ p: 2, background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 3 }}>
                <Chip label="SUSTAINABILITY METRIC" color="success" size="small" sx={{ fontWeight: 800, mb: 1 }} />
                <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  142.8 Tons CO₂ Emissions Prevented
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  AI multi-rider pooling achieved an average 3.2 riders per EV vehicle shift.
                </Typography>
              </Card>

              <Card sx={{ p: 2, background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 3 }}>
                <Chip label="SURGE PRICING COMPARISON" color="warning" size="small" sx={{ fontWeight: 800, mb: 1 }} />
                <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  ₹ 4.2 Lakhs Saved By Riders
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  Riders saved 38% compared to legacy competitor surge pricing models.
                </Typography>
              </Card>
            </Stack>
          </GlassCard>
        </Grid>

        {/* Right Demand Heatmap & Live Fleet Map */}
        <Grid item xs={12} md={8}>
          <InteractiveMap heatmapMode={true} heatmapCells={MOCK_DEMAND_HEATMAP_CELLS} height={560} />
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
