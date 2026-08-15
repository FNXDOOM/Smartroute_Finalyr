import React, { useEffect, useState } from 'react';
import { Box, Grid, Typography, Card, Chip, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { InteractiveMap } from '../../components/maps/InteractiveMap';
import { trackingApi } from '../../services/api';

export const FleetMap = () => {
  const [vehicles, setVehicles] = useState([]);
  useEffect(() => { trackingApi.getLiveFeed().then((d) => setVehicles(d.vehicles || [])).catch(() => {}); }, []);
  return (
    <DashboardLayout title="Live Fleet Telemetry & Tracking">
      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <InteractiveMap vehicles={vehicles} height={580} />
        </Grid>
        <Grid item xs={12} md={5}>
          <GlassCard sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 2 }}>
              Active Vehicle Roster ({vehicles.length})
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Vehicle / Plate</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Driver</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Battery</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {vehicles.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell sx={{ fontWeight: 700, color: '#00D4FF' }}>{v.license_plate}</TableCell>
                    <TableCell>{v.driver_name || '—'}</TableCell>
                    <TableCell><Chip label={v.status} color={v.status === 'active' ? 'success' : 'default'} size="small" /></TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{v.battery == null ? '—' : `${v.battery}%`}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </GlassCard>
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
