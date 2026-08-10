import React from 'react';
import { Box, Container, Grid } from '@mui/material';
import { StatCounter } from '../common/StatCounter';
import { Car, Building2, Leaf, Clock } from 'lucide-react';
import { GlassCard } from '../common/GlassCard';

export const StatsBand = () => {
  return (
    <Box
      sx={{
        py: 8,
        background: 'linear-gradient(180deg, rgba(11, 31, 58, 0.4) 0%, rgba(18, 18, 18, 0.8) 100%)',
        borderTop: '1px solid rgba(0, 212, 255, 0.15)',
        borderBottom: '1px solid rgba(0, 212, 255, 0.15)',
      }}
    >
      <Container maxWidth="xl">
        <Grid container spacing={3}>
          <Grid item xs={6} md={3}>
            <GlassCard hoverGlow={false} sx={{ py: 1 }}>
              <StatCounter value={48920} suffix="+" label="Rides Completed" icon={Car} />
            </GlassCard>
          </Grid>
          <Grid item xs={6} md={3}>
            <GlassCard hoverGlow={false} sx={{ py: 1 }}>
              <StatCounter value={12} suffix=" Tech Hubs" label="Cities Live" icon={Building2} />
            </GlassCard>
          </Grid>
          <Grid item xs={6} md={3}>
            <GlassCard hoverGlow={false} sx={{ py: 1 }}>
              <StatCounter value={142.8} suffix=" Tons" decimals={1} label="CO₂ Emissions Saved" icon={Leaf} />
            </GlassCard>
          </Grid>
          <Grid item xs={6} md={3}>
            <GlassCard hoverGlow={false} sx={{ py: 1 }}>
              <StatCounter value={6.4} suffix=" Mins" decimals={1} label="Avg Wait Time Reduction" icon={Clock} />
            </GlassCard>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};
