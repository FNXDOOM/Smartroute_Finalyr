import React from 'react';
import { Box, Container, Typography, Button, Stack } from '@mui/material';
import { ArrowRight, Zap, Car } from 'lucide-react';
import { Link as RouterLink } from 'react-router-dom';
import { GlassCard } from '../common/GlassCard';

export const CTABanner = ({ variant = 'rider' }) => {
  const isRider = variant === 'rider';

  return (
    <Container maxWidth="xl" sx={{ my: { xs: 6, md: 10 } }}>
      <GlassCard
        sx={{
          p: { xs: 4, md: 6 },
          borderRadius: 6,
          background: isRider
            ? 'linear-gradient(135deg, #0B1F3A 0%, #1E88E5 70%, #00D4FF 100%)'
            : 'linear-gradient(135deg, #1A2332 0%, #0B1F3A 70%, #10B981 100%)',
          position: 'relative',
          overflow: 'hidden',
          border: '1px solid rgba(0, 212, 255, 0.4)',
        }}
      >
        <Box sx={{ position: 'relative', zIndex: 2, maxWidth: 640 }}>
          <Typography variant="h3" sx={{ fontWeight: 800, color: '#FFFFFF', mb: 2 }}>
            {isRider ? 'Ready for Smarter, Surge-Free Rides?' : 'Drive with SmartRoute AI Fleet'}
          </Typography>
          <Typography variant="body1" sx={{ color: 'rgba(255, 255, 255, 0.85)', mb: 4, lineHeight: 1.7 }}>
            {isRider
              ? 'Join thousands of riders enjoying AI-grouped EV rides with transparent flat pricing and minimal wait times.'
              : 'Earn 35% higher hourly returns with zero empty miles between rides and AI pre-optimized route guidance.'}
          </Typography>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Button
              variant="contained"
              size="large"
              component={RouterLink}
              to={isRider ? '/signup' : '/signup?role=driver'}
              endIcon={<ArrowRight size={20} />}
              sx={{
                background: '#FFFFFF',
                color: '#0B1F3A',
                fontWeight: 800,
                px: 4,
                py: 1.5,
                '&:hover': {
                  background: '#F0F6FF',
                },
              }}
            >
              {isRider ? 'Book First Ride Now' : 'Apply as Driver Partner'}
            </Button>
          </Stack>
        </Box>
      </GlassCard>
    </Container>
  );
};
