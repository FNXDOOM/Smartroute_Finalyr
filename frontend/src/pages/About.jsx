import React from 'react';
import { Box, Container, Typography, Grid, Chip } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { GlassCard } from '../components/common/GlassCard';
import { Shield, Zap, Leaf, Award, Cpu, Users } from 'lucide-react';

export const About = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Container maxWidth="xl" sx={{ pt: 8, pb: 12, flexGrow: 1 }}>
        <Box sx={{ textAlign: 'center', mb: 8, maxWidth: 800, mx: 'auto' }}>
          <Chip label="OUR MISSION" color="primary" sx={{ mb: 2, fontWeight: 700 }} />
          <Typography variant="h2" sx={{ fontWeight: 800, mb: 2 }}>
            Pioneering Intelligent, Sustainable Shared Mobility
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', fontSize: '1.1rem', lineHeight: 1.8 }}>
            SmartRoute AI was built to solve last-mile urban congestion. Traditional ride-hailing app algorithms rely on reactive rerouting and dynamic surge pricing. We replace chaos with predictive AI clustering, graph optimization, and guaranteed flat fares.
          </Typography>
        </Box>

        <Grid container spacing={4} sx={{ mb: 10 }}>
          {[
            { title: 'Zero Surge Guarantee', desc: 'Predictable flat pricing regardless of weather or demand spikes.', icon: Zap },
            { title: 'AI-First Clustering', desc: 'Graph partitioners group riders by spatial trajectory in real-time.', icon: Cpu },
            { title: '100% EV Electric Fleet', desc: 'Zero tailpipe emissions and dedicated eco-impact counters.', icon: Leaf },
            { title: 'Safe Virtual Hubs', desc: 'Smart pickup points optimized for walking ease and passenger safety.', icon: Shield },
          ].map((item, i) => {
            const Icon = item.icon;
            return (
              <Grid item xs={12} sm={6} md={3} key={i}>
                <GlassCard sx={{ height: '100%', textCenter: 'center', textAlign: 'center' }}>
                  <Box
                    sx={{
                      width: 50,
                      height: 50,
                      borderRadius: 3,
                      background: 'rgba(0,212,255,0.1)',
                      color: '#00D4FF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      mx: 'auto',
                      mb: 2,
                    }}
                  >
                    <Icon size={26} />
                  </Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
                    {item.title}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {item.desc}
                  </Typography>
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
