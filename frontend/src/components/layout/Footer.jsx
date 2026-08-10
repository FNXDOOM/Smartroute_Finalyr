import React from 'react';
import { Box, Container, Grid, Typography, Button, TextField, Divider, Stack, IconButton } from '@mui/material';
import { Zap, Send, Shield, Heart } from 'lucide-react';
import { Link as RouterLink } from 'react-router-dom';

export const Footer = () => {
  return (
    <Box
      component="footer"
      sx={{
        backgroundColor: '#0B1F3A',
        color: '#FFFFFF',
        pt: { xs: 8, md: 10 },
        pb: 4,
        borderTop: '1px solid rgba(0, 212, 255, 0.2)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Background glow circle */}
      <Box
        sx={{
          position: 'absolute',
          top: -100,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 600,
          height: 300,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(30, 136, 229, 0.15) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      <Container maxWidth="xl">
        <Grid container spacing={4} sx={{ mb: 6 }}>
          {/* Brand Col */}
          <Grid item xs={12} md={4}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, mb: 2 }}>
              <Box
                sx={{
                  width: 40,
                  height: 40,
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Zap size={22} color="#FFFFFF" />
              </Box>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#FFFFFF' }}>
                SmartRoute<span style={{ color: '#00D4FF' }}>.AI</span>
              </Typography>
            </Box>
            <Typography variant="body2" sx={{ color: '#94A3B8', mb: 3, maxWidth: 360, lineHeight: 1.7 }}>
              Next-generation AI-powered shared mobility platform. Pre-dispatch route optimization, smart virtual pickup points, flat fares, and zero surge pricing.
            </Typography>

            <Stack direction="row" spacing={1}>
              {['github-icon', 'social-icon', 'bluesky-icon', 'discord-icon'].map((symId, i) => (
                <IconButton
                  key={i}
                  aria-label={symId.replace('-icon', '')}
                  sx={{
                    color: '#94A3B8',
                    border: '1px solid rgba(255,255,255,0.1)',
                    '&:hover': { color: '#00D4FF', borderColor: '#00D4FF', backgroundColor: 'rgba(0,212,255,0.1)' },
                  }}
                >
                  <svg width={18} height={18} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <use href={`/icons.svg#${symId}`} />
                  </svg>
                </IconButton>
              ))}
            </Stack>
          </Grid>

          {/* Quick Links */}
          <Grid item xs={6} sm={3} md={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 2 }}>
              Platform
            </Typography>
            <Stack spacing={1.2}>
              {['About Us', 'Features', 'How It Works', 'Pricing', 'Careers', 'Blog'].map((item) => (
                <Typography
                  key={item}
                  variant="body2"
                  component={RouterLink}
                  to={`/${item.toLowerCase().replace(/\s+/g, '-')}`}
                  sx={{
                    color: '#94A3B8',
                    textDecoration: 'none',
                    '&:hover': { color: '#00D4FF' },
                  }}
                >
                  {item}
                </Typography>
              ))}
            </Stack>
          </Grid>

          {/* Legal & Safety */}
          <Grid item xs={6} sm={3} md={2}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 2 }}>
              Legal & Safety
            </Typography>
            <Stack spacing={1.2}>
              {['Privacy Policy', 'Terms of Service', 'Safety Guidelines', 'Eco Impact Report', 'Driver Terms'].map((item) => (
                <Typography
                  key={item}
                  variant="body2"
                  component={RouterLink}
                  to="#"
                  sx={{
                    color: '#94A3B8',
                    textDecoration: 'none',
                    '&:hover': { color: '#00D4FF' },
                  }}
                >
                  {item}
                </Typography>
              ))}
            </Stack>
          </Grid>

          {/* Newsletter */}
          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 2 }}>
              Stay Updated with AI Mobility Insights
            </Typography>
            <Typography variant="body2" sx={{ color: '#94A3B8', mb: 2 }}>
              Subscribe to our monthly research newsletter on AI route optimization and sustainable transit.
            </Typography>

            <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
              <TextField
                placeholder="Enter your email"
                size="small"
                fullWidth
                sx={{
                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  borderRadius: 2,
                  input: { color: '#FFFFFF' },
                }}
              />
              <Button
                variant="contained"
                sx={{
                  background: 'linear-gradient(90deg, #1E88E5 0%, #00D4FF 100%)',
                  px: 3,
                  whiteSpace: 'nowrap',
                }}
              >
                <Send size={18} />
              </Button>
            </Box>

            {/* App Store / Google Play download buttons */}
            <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mb: 1 }}>
              Download Rider & Driver Apps:
            </Typography>
            <Stack direction="row" spacing={1.5}>
              <Button
                variant="outlined"
                size="small"
                sx={{
                  borderColor: 'rgba(255,255,255,0.2)',
                  color: '#FFFFFF',
                  textTransform: 'none',
                  borderRadius: 2,
                }}
              >
                App Store
              </Button>
              <Button
                variant="outlined"
                size="small"
                sx={{
                  borderColor: 'rgba(255,255,255,0.2)',
                  color: '#FFFFFF',
                  textTransform: 'none',
                  borderRadius: 2,
                }}
              >
                Google Play
              </Button>
            </Stack>
          </Grid>
        </Grid>

        <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.08)', my: 4 }} />

        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            © {new Date().getFullYear()} SmartRoute AI Inc. All rights reserved. Built with React & FastAPI.
          </Typography>
          <Typography variant="caption" sx={{ color: '#64748B', display: 'flex', alignItems: 'center', gap: 0.5 }}>
            Pioneering Eco-Friendly Transit <Heart size={14} color="#EF4444" fill="#EF4444" /> worldwide.
          </Typography>
        </Box>
      </Container>
    </Box>
  );
};
