import React from 'react';
import { Box, Container, Typography, Grid, TextField, Button } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { GlassCard } from '../components/common/GlassCard';
import { Mail, Phone, MapPin, Send } from 'lucide-react';

export const Contact = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Container maxWidth="lg" sx={{ pt: 8, pb: 12, flexGrow: 1 }}>
        <Box sx={{ textAlign: 'center', mb: 8 }}>
          <Typography variant="h2" sx={{ fontWeight: 800, mb: 2 }}>
            Contact & Support
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 540, mx: 'auto' }}>
            Have questions about enterprise fleets, partnerships, or rider support? Get in touch with our team.
          </Typography>
        </Box>

        <Grid container spacing={4}>
          <Grid item xs={12} md={5}>
            <GlassCard sx={{ p: 4, height: '100%' }}>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
                Get In Touch
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
                <Mail size={22} color="#00D4FF" />
                <Typography variant="body2">support@smartroute.ai</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
                <Phone size={22} color="#1E88E5" />
                <Typography variant="body2">+91 (080) 4920-8800</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 2 }}>
                <MapPin size={22} color="#10B981" />
                <Typography variant="body2">SmartRoute AI Tech Tower, Indiranagar 100ft Rd, Bengaluru, KA 560038</Typography>
              </Box>
            </GlassCard>
          </Grid>

          <Grid item xs={12} md={7}>
            <GlassCard sx={{ p: 4 }}>
              <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
                Send Us a Message
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth label="Full Name" placeholder="John Doe" />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth label="Email Address" placeholder="john@example.com" />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth label="Subject" placeholder="Fleet partnership or rider inquiry" />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth multiline rows={4} label="Message" placeholder="How can we help you?" />
                </Grid>
                <Grid item xs={12}>
                  <Button variant="contained" size="large" fullWidth endIcon={<Send size={18} />}>
                    Send Message
                  </Button>
                </Grid>
              </Grid>
            </GlassCard>
          </Grid>
        </Grid>
      </Container>
      <Footer />
    </Box>
  );
};
