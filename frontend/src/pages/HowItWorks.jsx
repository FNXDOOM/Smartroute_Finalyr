import React from 'react';
import { Box, Container, Typography, Grid, Paper, Step, Stepper, StepLabel, StepContent, Button } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { GlassCard } from '../components/common/GlassCard';
import { MapPin, Users, Route as RouteIcon, Car, CheckCircle } from 'lucide-react';

const STEPS = [
  {
    label: '1. Request Your Route',
    description: 'Enter your pickup point and destination. SmartRoute AI calculates flat-fare pricing upfront with zero surge pricing.',
    icon: MapPin,
  },
  {
    label: '2. AI Dynamic Grouping',
    description: 'Machine learning partitioners evaluate spatial trajectories in real time, matching you with up to 3 nearby riders going your way.',
    icon: Users,
  },
  {
    label: '3. Pre-Dispatch Graph Optimization',
    description: 'Our algorithms compute the complete multi-stop path before the vehicle is dispatched, preventing detours mid-trip.',
    icon: RouteIcon,
  },
  {
    label: '4. Smart Pickup at Virtual Hub',
    description: 'Walk 1-2 minutes to a safe, well-lit Smart Pickup Point to board your electric vehicle smoothly without traffic delays.',
    icon: Car,
  },
  {
    label: '5. Enjoy Zero-Emissions Flat Ride',
    description: 'Track your live vehicle telemetry, ETA, and cumulative CO₂ emissions saved directly from your smartphone.',
    icon: CheckCircle,
  },
];

export const HowItWorks = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Container maxWidth="lg" sx={{ pt: 8, pb: 12, flexGrow: 1 }}>
        <Box sx={{ textAlign: 'center', mb: 8 }}>
          <Typography variant="h2" sx={{ fontWeight: 800, mb: 2 }}>
            How SmartRoute AI Works
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 600, mx: 'auto' }}>
            5 simple steps to faster, fairer, eco-friendly shared transportation.
          </Typography>
        </Box>

        <Grid container spacing={4}>
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            return (
              <Grid item xs={12} key={idx}>
                <GlassCard sx={{ display: 'flex', alignItems: 'center', gap: 3, p: 3 }}>
                  <Box
                    sx={{
                      width: 60,
                      height: 60,
                      borderRadius: 4,
                      background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
                      color: '#FFFFFF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Icon size={28} />
                  </Box>
                  <Box>
                    <Typography variant="h5" sx={{ fontWeight: 700, mb: 0.5 }}>
                      {step.label}
                    </Typography>
                    <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.7 }}>
                      {step.description}
                    </Typography>
                  </Box>
                </GlassCard>
              </Grid>
            );
          })}
        </Grid>
      </Container>
      <Footer />
    </Box>
  );
};
