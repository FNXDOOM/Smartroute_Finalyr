import React, { useEffect, useState } from 'react';
import { Box, Grid, Typography, Button, Card, Avatar, Chip, Stack, Badge, Divider } from '@mui/material';
import { Car, Navigation, Check, X, Shield, Clock, Battery, Users, DollarSign, Award } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { InteractiveMap } from '../../components/maps/InteractiveMap';
import { ridesApi, trackingApi } from '../../services/api';

export const DriverOverview = () => {
  const [vehicle, setVehicle] = useState(null);
  const [activeTrip, setActiveTrip] = useState(null);
  const [requests, setRequests] = useState([]);
  useEffect(() => { Promise.all([trackingApi.getLiveFeed(), ridesApi.getAllRides({ status: 'pending' })]).then(([feed, rides]) => { setVehicle((feed.vehicles || [])[0] || null); setRequests((rides.rides || []).map((r) => ({ ...r, pickup: r.pickup_label || 'Pickup coordinates', destination: r.destination_label || 'Destination coordinates', fare: r.ride_option_price || 0, passengers: 1 }))); }).catch(() => {}); }, []);

  const handleAccept = async (req) => {
    await ridesApi.updateStatus(req.id, 'assigned');
    setActiveTrip(req);
    setRequests(requests.filter((r) => r.id !== req.id));
  };

  const handleDecline = (id) => {
    setRequests(requests.filter((r) => r.id !== id));
  };

  return (
    <DashboardLayout title="Driver Partner Dashboard">
      <Grid container spacing={3}>
        {/* Top Summary Cards */}
        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>TODAY'S EARNINGS</Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#00D4FF', mt: 0.5 }}>₹ 3,450</Typography>
            <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>+18% vs yesterday</Typography>
          </GlassCard>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>COMPLETED TRIPS</Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, mt: 0.5 }}>14 Rides</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>0 empty miles</Typography>
          </GlassCard>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>DRIVER RATING</Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#F59E0B', mt: 0.5 }}>4.92 ★</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>Top 5% Partner</Typography>
          </GlassCard>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <GlassCard sx={{ py: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>EV FLEET BATTERY</Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#10B981', mt: 0.5 }}>{vehicle?.battery == null ? '—' : `${vehicle.battery}%`}</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>{vehicle?.license_plate || 'Vehicle not assigned'}</Typography>
          </GlassCard>
        </Grid>

        {/* Live Navigation & Queue Panel */}
        <Grid item xs={12} md={5}>
          {activeTrip ? (
            <GlassCard sx={{ p: 3, mb: 3, border: '1px solid #00D4FF' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Chip label="ACTIVE NAVIGATION" color="success" sx={{ fontWeight: 800 }} />
                <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#00D4FF' }}>₹{activeTrip.fare}</Typography>
              </Box>

              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Pickup:</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>{activeTrip.pickup}</Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Destination:</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>{activeTrip.destination}</Typography>

              <Button fullWidth variant="contained" color="secondary" onClick={() => setActiveTrip(null)} sx={{ py: 1.2 }}>
                Complete Ride & Receive Payout
              </Button>
            </GlassCard>
          ) : (
            <GlassCard sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 800, mb: 2 }}>
                AI-Ranked Trip Requests Queue ({requests.length})
              </Typography>

              {requests.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
                  <Car size={36} color="#94A3B8" style={{ marginBottom: 8 }} />
                  <Typography variant="body2">No pending requests right now. Pre-positioning in zone...</Typography>
                </Box>
              ) : (
                <Stack spacing={2}>
                  {requests.map((req) => (
                    <Card key={req.id} sx={{ p: 2, borderRadius: 3, border: '1px solid rgba(0, 212, 255, 0.3)' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Chip label={`AI MATCH ${req.aiMatchScore}%`} color="primary" size="small" sx={{ fontWeight: 800 }} />
                        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#00D4FF' }}>₹{req.fare}</Typography>
                      </Box>

                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{req.pickup}</Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
                        → {req.destination} ({req.passengers} riders)
                      </Typography>

                      <Typography variant="caption" sx={{ color: '#10B981', display: 'block', mb: 2 }}>
                        {req.reason}
                      </Typography>

                      <Stack direction="row" spacing={1}>
                        <Button fullWidth variant="contained" size="small" startIcon={<Check size={16} />} onClick={() => handleAccept(req)}>
                          Accept Trip
                        </Button>
                        <Button fullWidth variant="outlined" color="error" size="small" startIcon={<X size={16} />} onClick={() => handleDecline(req.id)}>
                          Decline
                        </Button>
                      </Stack>
                    </Card>
                  ))}
                </Stack>
              )}
            </GlassCard>
          )}
        </Grid>

        {/* Live Driver Navigation Map */}
        <Grid item xs={12} md={7}>
          <InteractiveMap height={540} />
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
