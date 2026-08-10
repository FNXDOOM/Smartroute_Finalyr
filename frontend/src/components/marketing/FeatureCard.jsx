import React from 'react';
import { Box, Container, Grid, Typography } from '@mui/material';
import { Cpu, Users, Route as RouteIcon, MapPin, DollarSign, Leaf } from 'lucide-react';
import { motion } from 'framer-motion';
import { GlassCard } from '../common/GlassCard';

export const FEATURES_DATA = [
  {
    icon: Cpu,
    title: 'AI Demand Forecasting',
    description: 'Machine learning algorithms anticipate passenger demand patterns across H3 spatial zones up to 2 hours before peak hours, pre-positioning EV fleets to eliminate wait times.',
    color: '#00D4FF',
  },
  {
    icon: Users,
    title: 'Smart Ride Grouping',
    description: 'AI matches compatible riders moving along overlapping trajectories in real time, avoiding manual searching and providing shared rides with maximum comfort and privacy.',
    color: '#1E88E5',
  },
  {
    icon: RouteIcon,
    title: 'Pre-Dispatch Routing',
    description: 'Unlike legacy ride-hailing apps that re-route reactively, SmartRoute AI calculates end-to-end optimal paths before vehicle dispatch to guarantee punctual arrivals.',
    color: '#3B82F6',
  },
  {
    icon: MapPin,
    title: 'Smart Virtual Pickup Points',
    description: 'AI identifies easy-access, safe virtual pickup hubs within a 2-minute walk, bypassing narrow streets, traffic chokepoints, and vehicle turnarounds.',
    color: '#10B981',
  },
  {
    icon: DollarSign,
    title: 'Flat-Fare Pricing',
    description: 'Transparent, predictable flat rates with zero surge pricing during rain, rush hours, or high demand. What you see upfront is exactly what you pay.',
    color: '#F59E0B',
  },
  {
    icon: Leaf,
    title: 'Eco-Friendly Impact',
    description: 'Every pooled EV trip reduces urban carbon footprint. Track your individual and cumulative CO₂ emissions saved directly in your rider dashboard.',
    color: '#10B981',
  },
];

export const FeatureSection = () => {
  return (
    <Box sx={{ py: { xs: 8, md: 12 }, position: 'relative' }}>
      <Container maxWidth="xl">
        <Box sx={{ textAlign: 'center', mb: 8 }}>
          <Typography
            variant="caption"
            sx={{
              color: '#00D4FF',
              fontWeight: 800,
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
            }}
          >
            Core Technology Differentiators
          </Typography>
          <Typography variant="h2" sx={{ fontWeight: 800, mt: 1.5, mb: 2 }}>
            Engineered for Modern Shared Mobility
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 640, mx: 'auto' }}>
            SmartRoute AI eliminates the inefficiencies of traditional ride-hailing by pairing advanced AI clustering with flat-fare transparency.
          </Typography>
        </Box>

        <Grid container spacing={4}>
          {FEATURES_DATA.map((feat, i) => {
            const Icon = feat.icon;
            return (
              <Grid item xs={12} sm={6} md={4} key={feat.title}>
                <GlassCard
                  initial={{ opacity: 0, y: 30 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: i * 0.1 }}
                  sx={{ height: '100%' }}
                >
                  <Box
                    sx={{
                      width: 52,
                      height: 52,
                      borderRadius: '16px',
                      background: `linear-gradient(135deg, ${feat.color}25 0%, rgba(11, 31, 58, 0.5) 100%)`,
                      border: `1px solid ${feat.color}50`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      mb: 2.5,
                      color: feat.color,
                    }}
                  >
                    <Icon size={26} />
                  </Box>

                  <Typography variant="h5" sx={{ fontWeight: 700, mb: 1.5 }}>
                    {feat.title}
                  </Typography>

                  <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.7 }}>
                    {feat.description}
                  </Typography>
                </GlassCard>
              </Grid>
            );
          })}
        </Grid>
      </Container>
    </Box>
  );
};
