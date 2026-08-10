import React from 'react';
import { Box } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { HeroSection } from '../components/marketing/HeroSection';
import { FeatureSection } from '../components/marketing/FeatureCard';
import { StatsBand } from '../components/marketing/StatsBand';
import { Testimonials } from '../components/marketing/Testimonials';
import { FAQSection } from '../components/marketing/FAQSection';
import { CTABanner } from '../components/marketing/CTABanner';

export const Home = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Box component="main" sx={{ flexGrow: 1 }}>
        <HeroSection />
        <FeatureSection />
        <StatsBand />
        <Testimonials />
        <FAQSection />
        <CTABanner variant="rider" />
      </Box>
      <Footer />
    </Box>
  );
};
