import React, { useState } from 'react';
import { Box, Container, Grid, Typography, Button, TextField, InputAdornment, Chip, Stack } from '@mui/material';
import { MapPin, Navigation, ArrowRight, Zap, ShieldCheck, Users, Clock, Leaf } from 'lucide-react';
import { motion } from 'framer-motion';
import { GlassCard } from '../common/GlassCard';
import { InteractiveMap } from '../maps/InteractiveMap';
import { useNavigate } from 'react-router-dom';

export const HeroSection = () => {
  const navigate = useNavigate();
  const [pickup, setPickup] = useState('Indiranagar Metro Exit 2, Bengaluru');
  const [destination, setDestination] = useState('Embassy TechVillage, ORR');

  const handleBookNow = () => {
    navigate('/rider-dashboard', { state: { pickup, destination } });
  };

  return (
    <Box
      sx={{
        position: 'relative',
        minHeight: { xs: 'auto', md: '90vh' },
        pt: { xs: 6, md: 10 },
        pb: { xs: 8, md: 12 },
        display: 'flex',
        alignItems: 'center',
        overflow: 'hidden',
      }}
    >
      {/* Glow gradient backdrops */}
      <Box
        sx={{
          position: 'absolute',
          top: -150,
          right: -100,
          width: 550,
          height: 550,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0, 212, 255, 0.15) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          bottom: -100,
          left: -100,
          width: 500,
          height: 500,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(30, 136, 229, 0.18) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      <Container maxWidth="xl">
        <Grid container spacing={5} alignItems="center">
          {/* Left Hero Text + Booking Overlay */}
          <Grid item xs={12} md={6}>
            <motion.div
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.7 }}
            >
              <Chip
                icon={<Zap size={16} color="#00D4FF" />}
                label="AI-POWERED CITY RIDES · BENGALURU"
                sx={{
                  backgroundColor: 'rgba(0, 212, 255, 0.12)',
                  borderColor: 'rgba(0, 212, 255, 0.4)',
                  borderWidth: 1,
                  borderStyle: 'solid',
                  color: '#00D4FF',
                  fontWeight: 800,
                  fontSize: '0.75rem',
                  mb: 3,
                  py: 0.5,
                }}
              />

              <Typography
                variant="h1"
                sx={{
                  fontWeight: 800,
                  fontSize: { xs: '2.5rem', sm: '3.5rem', lg: '4.2rem' },
                  lineHeight: 1.1,
                  mb: 2.5,
                }}
              >
                Your city ride,{' '}
                <span style={{
                  background: 'linear-gradient(90deg, #1E88E5 0%, #00D4FF 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}>
                  intelligently shared
                </span>{' '}
                .
              </Typography>

              <Typography
                variant="h6"
                sx={{
                  color: 'text.secondary',
                  fontWeight: 400,
                  lineHeight: 1.6,
                  mb: 4,
                  maxWidth: 540,
                }}
              >
                Get where you’re going with transparent fares, electric vehicles, and pickup points designed around your day.
              </Typography>
            </motion.div>

            {/* Booking Card Overlay */}
            <GlassCard
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              sx={{ p: 3, borderRadius: 4, border: '1px solid rgba(0, 212, 255, 0.3)' }}
            >
              <Typography variant="h5" sx={{ fontWeight: 800, mb: 0.5 }}>
                Where are you going?
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2.5 }}>Book in seconds. Know your fare before you ride.</Typography>

              <Stack spacing={2} sx={{ mb: 2.5 }}>
                <TextField
                  fullWidth
                  placeholder="Pickup location"
                  value={pickup}
                  onChange={(e) => setPickup(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <MapPin size={20} color="#1E88E5" />
                      </InputAdornment>
                    ),
                  }}
                />
                <TextField
                  fullWidth
                  placeholder="Where to?"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Navigation size={20} color="#00D4FF" />
                      </InputAdornment>
                    ),
                  }}
                />
              </Stack>

              <Button
                variant="contained"
                fullWidth
                size="large"
                onClick={handleBookNow}
                endIcon={<ArrowRight size={20} />}
                sx={{ py: 1.6, fontSize: '1.05rem' }}
              >
                Find my ride
              </Button>
              <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap' }}>
                <Chip size="small" icon={<ShieldCheck size={14} />} label="Verified drivers" variant="outlined" />
                <Chip size="small" icon={<Clock size={14} />} label="No surge pricing" variant="outlined" />
                <Chip size="small" icon={<Leaf size={14} />} label="100% electric fleet" variant="outlined" />
              </Stack>
            </GlassCard>
          </Grid>

          {/* Right Live Simulated Map + Floating AI Insight Chips */}
          <Grid item xs={12} md={6}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.3 }}
              style={{ position: 'relative' }}
            >
              {/* Animated Floating Glassmorphism Cards */}
              <GlassCard
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.6 }}
                sx={{
                  position: 'absolute',
                  top: 20,
                  right: 20,
                  zIndex: 10,
                  py: 1,
                  px: 2,
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(0,212,255,0.4)',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Users size={20} color="#00D4FF" />
                  <Box>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#00D4FF', display: 'block' }}>
                      AI Ride Grouping
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      3 compatible riders matched nearby
                    </Typography>
                  </Box>
                </Box>
              </GlassCard>

              <GlassCard
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.8 }}
                sx={{
                  position: 'absolute',
                  bottom: 25,
                  left: 20,
                  zIndex: 10,
                  py: 1,
                  px: 2,
                  backdropFilter: 'blur(16px)',
                  border: '1px solid rgba(16, 185, 129, 0.4)',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Leaf size={20} color="#10B981" />
                  <Box>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#10B981', display: 'block' }}>
                      Sustainable Impact
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      -1.4 kg CO₂ saved on this route
                    </Typography>
                  </Box>
                </Box>
              </GlassCard>

              {/* Map Preview */}
              <Box sx={{ borderRadius: 5, overflow: 'hidden', border: '1px solid rgba(0,212,255,.25)', boxShadow: '0 24px 70px rgba(0,0,0,.35)' }}>
                <InteractiveMap height={480} />
              </Box>
            </motion.div>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};
