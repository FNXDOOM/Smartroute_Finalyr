import React from 'react';
import { Box, Grid, Typography, Card, LinearProgress } from '@mui/material';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { Leaf, Cpu, TrendingUp, Clock, Zap } from 'lucide-react';

export const Analytics = () => {
  return (
    <DashboardLayout title="AI Route Optimization & CO₂ Analytics">
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Before vs. After AI Route Optimization
            </Typography>

            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Average Passenger Wait Time</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#10B981' }}>-42% Reduction (14.2m → 6.4m)</Typography>
              </Box>
              <LinearProgress variant="determinate" value={58} color="success" sx={{ height: 10, borderRadius: 4 }} />
            </Box>

            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Fleet Empty Miles Traveled</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#00D4FF' }}>-65% Deadhead Miles</Typography>
              </Box>
              <LinearProgress variant="determinate" value={35} color="primary" sx={{ height: 10, borderRadius: 4 }} />
            </Box>

            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Rider Satisfaction Score</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#F59E0B' }}>94.8% Approval</Typography>
              </Box>
              <LinearProgress variant="determinate" value={95} color="warning" sx={{ height: 10, borderRadius: 4 }} />
            </Box>
          </GlassCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Environmental CO₂ Saved Counter
            </Typography>

            <Box sx={{ textAlign: 'center', py: 2 }}>
              <Leaf size={48} color="#10B981" style={{ marginBottom: 12 }} />
              <Typography variant="h3" sx={{ fontWeight: 800, color: '#10B981', mb: 0.5 }}>
                142.8 Metric Tons
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 3 }}>
                Cumulative Carbon Dioxide Offset by SmartRoute AI EV Pooling
              </Typography>
            </Box>
          </GlassCard>
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
