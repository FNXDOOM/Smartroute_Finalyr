import React from 'react';
import { Box, Grid, Typography, LinearProgress } from '@mui/material';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { Award, Zap, ThumbsUp, ShieldCheck } from 'lucide-react';

export const Performance = () => {
  return (
    <DashboardLayout title="Driver Performance & Ratings">
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Driver Rating Breakdown
            </Typography>

            <Box sx={{ textAlign: 'center', mb: 4 }}>
              <Typography variant="h2" sx={{ fontWeight: 800, color: '#F59E0B' }}>4.92 ★</Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>Based on 482 rider reviews</Typography>
            </Box>

            <Stack spacing={2} sx={{ mb: 2 }}>
              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Typography variant="body2">Trip Acceptance Rate</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: '#00D4FF' }}>96%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={96} sx={{ height: 8, borderRadius: 4 }} />
              </Box>

              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Typography variant="body2">Punctuality Score</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: '#10B981' }}>98%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={98} color="success" sx={{ height: 8, borderRadius: 4 }} />
              </Box>
            </Stack>
          </GlassCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Partner Badges & Rewards
            </Typography>

            <Stack spacing={2}>
              {[
                { title: 'Top AI Route Optimizer', desc: 'Maintained 0 detour minutes for 30 consecutive trips.', icon: Zap },
                { title: 'Zero Emissions Champion', desc: 'Saved over 250kg of CO₂ with EV Tata Nexon.', icon: ShieldCheck },
                { title: 'Customer Favorite', desc: 'Achieved 5-star ratings on 95%+ of trips this month.', icon: ThumbsUp },
              ].map((badge, i) => {
                const Icon = badge.icon;
                return (
                  <Box key={i} sx={{ p: 2, borderRadius: 3, background: 'rgba(255,255,255,0.04)', display: 'flex', gap: 2, alignItems: 'center' }}>
                    <Box sx={{ width: 42, height: 42, borderRadius: 3, background: 'rgba(0,212,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#00D4FF' }}>
                      <Icon size={22} />
                    </Box>
                    <Box>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{badge.title}</Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>{badge.desc}</Typography>
                    </Box>
                  </Box>
                );
              })}
            </Stack>
          </GlassCard>
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
