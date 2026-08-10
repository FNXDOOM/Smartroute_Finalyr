import React, { useState } from 'react';
import { Box, Typography, Tabs, Tab, Button, Card, Stack, Chip, TextField } from '@mui/material';
import { CreditCard, Wallet, QrCode, ShieldCheck, CheckCircle } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';

export const PaymentMethods = () => {
  const [tab, setTab] = useState(0);

  return (
    <DashboardLayout title="Payment Methods & Wallet">
      <GlassCard sx={{ p: 4, maxWidth: 800 }}>
        <Typography variant="h6" sx={{ fontWeight: 800, mb: 1 }}>
          Payment Settings
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
          Manage your flat-fare payment options. Integrated with Razorpay, UPI, and SmartWallet.
        </Typography>

        <Tabs
          value={tab}
          onChange={(e, val) => setTab(val)}
          sx={{
            mb: 4,
            borderBottom: '1px solid rgba(255,255,255,0.1)',
            '& .MuiTab-root': { fontWeight: 700, textTransform: 'none' },
          }}
        >
          <Tab label="UPI / QR Code" />
          <Tab label="Credit / Debit Card" />
          <Tab label="SmartWallet Balance" />
          <Tab label="Razorpay Checkout" />
        </Tabs>

        {tab === 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2 }}>
              Saved UPI IDs:
            </Typography>
            <Stack spacing={2} sx={{ mb: 3 }}>
              <Card sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderRadius: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <QrCode size={24} color="#00D4FF" />
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Google Pay / UPI</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>aarav.mehta@okicici</Typography>
                  </Box>
                </Box>
                <Chip label="DEFAULT" color="primary" size="small" />
              </Card>
            </Stack>
            <Button variant="outlined">Add New UPI ID</Button>
          </Box>
        )}

        {tab === 1 && (
          <Box component="form">
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField fullWidth label="Cardholder Name" placeholder="Aarav Mehta" />
              </Grid>
              <Grid item xs={12}>
                <TextField fullWidth label="Card Number" placeholder="4532 •••• •••• 8810" />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth label="Expiry Date" placeholder="08 / 29" />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth label="CVV" placeholder="•••" type="password" />
              </Grid>
              <Grid item xs={12}>
                <Button variant="contained" fullWidth sx={{ py: 1.4 }}>Save Card</Button>
              </Grid>
            </Grid>
          </Box>
        )}

        {tab === 2 && (
          <Box sx={{ textAlign: 'center', py: 3 }}>
            <Wallet size={48} color="#00D4FF" style={{ marginBottom: 12 }} />
            <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>₹ 1,250.00</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 3 }}>
              SmartWallet Available Auto-Pay Balance
            </Typography>
            <Button variant="contained" size="large">Add Funds to Wallet</Button>
          </Box>
        )}

        {tab === 3 && (
          <Box sx={{ p: 3, textAlign: 'center', background: 'rgba(30, 136, 229, 0.1)', borderRadius: 4 }}>
            <ShieldCheck size={36} color="#00D4FF" style={{ marginBottom: 8 }} />
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>Razorpay Secured Checkout</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
              One-click checkout supporting Net Banking, EMI, and International Cards.
            </Typography>
            <Button variant="contained" color="secondary" size="large">Launch Razorpay Gateway UI</Button>
          </Box>
        )}
      </GlassCard>
    </DashboardLayout>
  );
};
