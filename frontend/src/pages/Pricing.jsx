import React from 'react';
import { Box, Container, Typography, Grid, Table, TableBody, TableCell, TableHead, TableRow, Chip } from '@mui/material';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { GlassCard } from '../components/common/GlassCard';
import { Check, X, Shield, Zap } from 'lucide-react';

export const Pricing = () => {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <Container maxWidth="lg" sx={{ pt: 8, pb: 12, flexGrow: 1 }}>
        <Box sx={{ textAlign: 'center', mb: 8 }}>
          <Chip label="TRANSPARENT FARES" color="secondary" sx={{ mb: 2, fontWeight: 700 }} />
          <Typography variant="h2" sx={{ fontWeight: 800, mb: 2 }}>
            Flat-Fare Pricing vs. Legacy Surge Pricing
          </Typography>
          <Typography variant="body1" sx={{ color: 'text.secondary', maxWidth: 640, mx: 'auto' }}>
            Never pay double for rain or peak office hours. SmartRoute AI guarantees transparent, predictable fares for every journey.
          </Typography>
        </Box>

        <GlassCard sx={{ p: 4, mb: 8 }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 800, fontSize: '1.05rem' }}>Feature / Condition</TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: '1.05rem', color: '#00D4FF' }}>SmartRoute AI</TableCell>
                <TableCell sx={{ fontWeight: 800, fontSize: '1.05rem', color: 'text.secondary' }}>Legacy Ride-Hailing Apps</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {[
                { feature: 'Monsoon / Heavy Rain Pricing', smart: 'Flat Fare (₹140 fixed)', legacy: '2.8x Surge (₹390+)' },
                { feature: '8 AM Rush Hour Pricing', smart: 'Flat Fare (₹140 fixed)', legacy: '2.2x Surge (₹310)' },
                { feature: 'Pre-Dispatch Route Optimization', smart: 'Yes (Calculated Before Trip)', legacy: 'No (Reactive Mid-Trip)' },
                { feature: 'Smart Virtual Pickup Hubs', smart: 'Yes (2-Min Safe Walk)', legacy: 'No (Door-to-Door Traffic Jam)' },
                { feature: 'CO₂ Emission Savings Report', smart: 'Included in Dashboard', legacy: 'Not Available' },
              ].map((row, i) => (
                <TableRow key={i}>
                  <TableCell sx={{ fontWeight: 600 }}>{row.feature}</TableCell>
                  <TableCell sx={{ color: '#00D4FF', fontWeight: 700 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Check size={18} color="#00D4FF" /> {row.smart}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ color: 'text.secondary' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <X size={18} color="#EF4444" /> {row.legacy}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </GlassCard>
      </Container>
      <Footer />
    </Box>
  );
};
