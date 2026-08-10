import React from 'react';
import { Box, Container, Typography } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { FeatureSection } from '../components/marketing/FeatureCard';

export const Features = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Box sx={{ pt: 6, flexGrow: 1 }}>
        <Container maxWidth="md" sx={{ textAlign: 'center', mb: 2 }}>
          <Typography variant="h2" sx={{ fontWeight: 800 }}>
            Platform Features & AI Innovation
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', mt: 2 }}>
            Explore how SmartRoute AI replaces legacy ride-hailing inefficiencies with intelligent pre-dispatch calculations.
          </Typography>
        </Container>
        <FeatureSection />
      </Box>
      <Footer />
    </Box>
  );
};
