import React from 'react';
import { Box, Container, Grid, Typography, Avatar, Rating } from '@mui/material';
import { GlassCard } from '../common/GlassCard';
import { Quote } from 'lucide-react';

const TESTIMONIALS = [
  {
    quote: 'SmartRoute AI has transformed my daily commute to Whitefield IT Park. The flat-fare guarantee saved me thousands during monsoon peak hours, and the smart pickup hub is just a 2-minute walk from my apartment.',
    name: 'Aarav Mehta',
    role: 'Senior Software Engineer',
    rating: 5,
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80',
  },
  {
    quote: 'As an EV driver partner, SmartRoute AI gives me optimized route sequences before I start my shift. Zero empty miles between pickups means higher hourly earnings and predictable daily income.',
    name: 'Vikram Singh',
    role: 'Electric Fleet Driver Partner',
    rating: 5,
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80',
  },
  {
    quote: 'Our company tech team loves the carbon reduction counter! SmartRoute AI allows our employees to share rides seamlessly while maintaining 100% flat fares and safe virtual pickup points.',
    name: 'Ananya Deshmukh',
    role: 'HR Lead at TechCorp',
    rating: 5,
    avatar: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=150&q=80',
  },
];

export const Testimonials = () => {
  return (
    <Box sx={{ py: { xs: 8, md: 12 } }}>
      <Container maxWidth="xl">
        <Box sx={{ textAlign: 'center', mb: 8 }}>
          <Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 800, letterSpacing: '0.15em' }}>
            USER FEEDBACK
          </Typography>
          <Typography variant="h2" sx={{ fontWeight: 800, mt: 1 }}>
            Loved by Riders & Drivers Alike
          </Typography>
        </Box>

        <Grid container spacing={4}>
          {TESTIMONIALS.map((t, idx) => (
            <Grid item xs={12} md={4} key={idx}>
              <GlassCard
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: idx * 0.15 }}
                sx={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
              >
                <Box>
                  <Box sx={{ color: '#00D4FF', mb: 2 }}>
                    <Quote size={32} />
                  </Box>
                  <Typography variant="body1" sx={{ fontStyle: 'italic', mb: 3, lineHeight: 1.7, color: 'text.primary' }}>
                    "{t.quote}"
                  </Typography>
                </Box>

                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <Avatar src={t.avatar} sx={{ width: 48, height: 48 }} />
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {t.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                      {t.role}
                    </Typography>
                    <Rating value={t.rating} readOnly size="small" sx={{ mt: 0.5 }} />
                  </Box>
                </Box>
              </GlassCard>
            </Grid>
          ))}
        </Grid>
      </Container>
    </Box>
  );
};
