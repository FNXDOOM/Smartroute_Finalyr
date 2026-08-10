import React from 'react';
import { Box, Grid, Typography, Table, TableBody, TableCell, TableHead, TableRow, Chip } from '@mui/material';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { DollarSign, TrendingUp, Calendar, ArrowUpRight } from 'lucide-react';

export const Earnings = () => {
  return (
    <DashboardLayout title="Driver Earnings & Payouts">
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={4}>
          <GlassCard sx={{ p: 3 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>TODAY'S PAYOUT</Typography>
            <Typography variant="h3" sx={{ fontWeight: 800, color: '#00D4FF', my: 0.5 }}>₹ 3,450</Typography>
            <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>Auto-credited at midnight</Typography>
          </GlassCard>
        </Grid>
        <Grid item xs={12} sm={4}>
          <GlassCard sx={{ p: 3 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>THIS WEEK</Typography>
            <Typography variant="h3" sx={{ fontWeight: 800, my: 0.5 }}>₹ 22,800</Typography>
            <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>+24% vs average driver</Typography>
          </GlassCard>
        </Grid>
        <Grid item xs={12} sm={4}>
          <GlassCard sx={{ p: 3 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>THIS MONTH</Typography>
            <Typography variant="h3" sx={{ fontWeight: 800, color: '#10B981', my: 0.5 }}>₹ 94,500</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>84 Trips Completed</Typography>
          </GlassCard>
        </Grid>
      </Grid>

      <GlassCard sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
          Recent Payout Transfers
        </Typography>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Payout ID</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Transfer Date</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Trips Count</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Gross Fare</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {[
              { id: 'PAY-9012', date: '09 Aug 2026', count: 12, amount: 3200, status: 'Completed' },
              { id: 'PAY-9011', date: '08 Aug 2026', count: 14, amount: 3650, status: 'Completed' },
              { id: 'PAY-9010', date: '07 Aug 2026', count: 11, amount: 2900, status: 'Completed' },
            ].map((row) => (
              <TableRow key={row.id}>
                <TableCell sx={{ fontWeight: 700, color: '#00D4FF' }}>{row.id}</TableCell>
                <TableCell>{row.date}</TableCell>
                <TableCell>{row.count} rides</TableCell>
                <TableCell sx={{ fontWeight: 800 }}>₹{row.amount}</TableCell>
                <TableCell><Chip label={row.status} color="success" size="small" /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </GlassCard>
    </DashboardLayout>
  );
};
