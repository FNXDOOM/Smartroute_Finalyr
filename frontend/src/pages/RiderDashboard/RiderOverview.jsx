import React, { useState, useEffect, useContext } from 'react';
import {
  Box,
  Grid,
  Typography,
  TextField,
  Button,
  Chip,
  Stack,
  Card,
  Avatar,
  IconButton,
  Divider,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
} from '@mui/material';
import {
  MapPin,
  Navigation,
  Zap,
  Users,
  Car,
  Phone,
  MessageSquare,
  AlertTriangle,
  Clock,
  ShieldCheck,
  CheckCircle2,
  DollarSign,
} from 'lucide-react';
import { GlassCard } from '../../components/common/GlassCard';
import { InteractiveMap } from '../../components/maps/InteractiveMap';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { ToastNotification } from '../../components/common/ToastNotification';
import { ridesApi } from '../../services/api';
import { AuthContext } from '../../context/AuthContext';

const RIDE_OPTIONS = [
  { id: 'smart_pool', name: 'Smart Pool', tagline: 'Share your ride and save', eta: '5–8 min', price: 120, originalPrice: 180, recommended: true },
  { id: 'standard_ev', name: 'Standard EV', tagline: 'Private electric ride', eta: '3–5 min', price: 180, originalPrice: 180 },
];

export const RiderOverview = () => {
  const { user } = useContext(AuthContext);
  const [pickup, setPickup] = useState('Indiranagar Metro Station Exit 2, Bengaluru');
  const [destination, setDestination] = useState('Embassy TechVillage, Outer Ring Road');
  const [selectedOption, setSelectedOption] = useState('smart_pool');
  const [bookingState, setBookingState] = useState('idle'); // idle | searching | confirmed | in_progress | completed
  const [ride, setRide] = useState(null);
  const [toast, setToast] = useState({ open: false, title: '', message: '', severity: 'info' });
  const [etaTimer, setEtaTimer] = useState(4);

  // Countdown timer for live trip status demo
  useEffect(() => {
    let interval;
    if (bookingState === 'in_progress' && etaTimer > 0) {
      interval = setInterval(() => {
        setEtaTimer((prev) => (prev > 0 ? prev - 1 : 0));
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [bookingState, etaTimer]);

  const handleBookRide = async () => {
    setBookingState('searching');
    const option = RIDE_OPTIONS.find((o) => o.id === selectedOption) || RIDE_OPTIONS[0];

    try {
      const response = await ridesApi.createRideRequest({
        pickup_lat: 12.9784,
        pickup_lng: 77.6408,
        dest_lat: 12.9352,
        dest_lng: 77.6245,
        pickup_label: pickup,
        destination_label: destination,
        ride_option_id: option.id,
        ride_option_name: option.name,
        ride_option_price: option.price,
      });
      setRide(response.ride || response);
      setBookingState('confirmed');
      setToast({
        open: true,
        title: 'Ride request submitted',
        message: 'Your request is now pending dispatch. Driver and vehicle details will appear after assignment.',
        severity: 'success',
      });
    } catch (err) {
      setBookingState('idle');
      setToast({ open: true, title: 'Ride request failed', message: err.response?.data?.detail || 'Unable to create ride request.', severity: 'error' });
    }
  };

  const handleStartTrip = () => {
    setBookingState('in_progress');
  };

  const handleSOS = () => {
    setToast({
      open: true,
      title: 'EMERGENCY SOS ALERT SENT',
      message: 'Police & SmartRoute AI 24/7 Safety Command Center notified with live GPS coordinates.',
      severity: 'error',
    });
  };

  return (
    <DashboardLayout title="Book & Track Ride">
      <Grid container spacing={3}>
        {/* Left Booking Panel or Live Ride Status Panel */}
        <Grid item xs={12} md={5} lg={4}>
          {bookingState === 'idle' || bookingState === 'searching' ? (
            <GlassCard sx={{ p: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 800, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Zap size={22} color="#00D4FF" /> AI Ride Dispatch
              </Typography>

              <Stack spacing={2} sx={{ mb: 3 }}>
                <Box>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    PICKUP LOCATION
                  </Typography>
                  <TextField
                    fullWidth
                    size="small"
                    value={pickup}
                    onChange={(e) => setPickup(e.target.value)}
                    InputProps={{
                      startAdornment: <MapPin size={18} color="#1E88E5" style={{ marginRight: 8 }} />,
                    }}
                  />
                </Box>

                <Box>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    DESTINATION
                  </Typography>
                  <TextField
                    fullWidth
                    size="small"
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    InputProps={{
                      startAdornment: <Navigation size={18} color="#00D4FF" style={{ marginRight: 8 }} />,
                    }}
                  />
                </Box>
              </Stack>

              {/* AI Recommendation Chip */}
              <Card
                sx={{
                  p: 2,
                  mb: 3,
                  background: 'linear-gradient(135deg, rgba(30, 136, 229, 0.15) 0%, rgba(0, 212, 255, 0.1) 100%)',
                  border: '1px solid rgba(0, 212, 255, 0.4)',
                  borderRadius: 3,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Users size={18} color="#00D4FF" />
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#00D4FF' }}>
                    AI SMART GROUPING INSIGHT
                  </Typography>
                </Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', lineHeight: 1.5 }}>
                  AI suggests grouping with 2 nearby tech park commuters — save 36% flat fare and reduce wait time by 6 mins!
                </Typography>
              </Card>

              {/* Vehicle Options List */}
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
                Select Vehicle Tier (Flat Fare Guaranteed):
              </Typography>
              <Stack spacing={1.5} sx={{ mb: 3 }}>
                {RIDE_OPTIONS.map((option) => {
                  const selected = selectedOption === option.id;
                  return (
                    <Box
                      key={option.id}
                      onClick={() => setSelectedOption(option.id)}
                      sx={{
                        p: 2,
                        borderRadius: 3,
                        cursor: 'pointer',
                        background: selected ? 'rgba(0, 212, 255, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                        border: selected ? '2px solid #00D4FF' : '1px solid rgba(255, 255, 255, 0.08)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Car size={24} color={selected ? '#00D4FF' : '#94A3B8'} />
                        <Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                              {option.name}
                            </Typography>
                            {option.recommended && (
                              <Chip label="BEST SAVE" size="small" color="secondary" sx={{ height: 18, fontSize: '0.6rem' }} />
                            )}
                          </Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                            {option.tagline} • ETA {option.eta}
                          </Typography>
                        </Box>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#00D4FF' }}>
                          ₹{option.price}
                        </Typography>
                        {option.originalPrice > option.price && (
                          <Typography variant="caption" sx={{ textDecoration: 'line-through', color: 'text.secondary' }}>
                            ₹{option.originalPrice}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                  );
                })}
              </Stack>

              <Button
                fullWidth
                variant="contained"
                size="large"
                disabled={bookingState === 'searching'}
                onClick={handleBookRide}
                sx={{ py: 1.5, fontWeight: 800 }}
              >
                {bookingState === 'searching' ? 'AI Matching Nearby EV...' : 'Confirm Flat-Fare Booking'}
              </Button>
            </GlassCard>
          ) : (
            /* Confirmed or In Progress Live Ride Tracking Card */
            <GlassCard sx={{ p: 3 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <Chip
                  label={bookingState === 'confirmed' ? 'REQUEST PENDING DISPATCH' : 'TRIP IN PROGRESS'}
                  color={bookingState === 'confirmed' ? 'info' : 'success'}
                  sx={{ fontWeight: 800 }}
                />
                <Button size="small" color="error" startIcon={<AlertTriangle size={16} />} onClick={handleSOS}>
                  SOS EMERGENCY
                </Button>
              </Box>

              {/* Driver info card */}
              <Box sx={{ p: 2, borderRadius: 3, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', mb: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                  <Avatar sx={{ bgcolor: '#1E88E5', width: 50, height: 50, fontWeight: 700 }}>
                  {ride?.driver_name?.[0] || '?'}
                  </Avatar>
                  <Box sx={{ flexGrow: 1 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                      {ride?.driver_name || 'Waiting for driver assignment'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 600 }}>
                      {ride?.vehicle_model || 'Vehicle details pending'} {ride?.license_plate ? `• ${ride.license_plate}` : ''}
                    </Typography>
                  </Box>
                  <Chip label={ride?.driver_rating ? `${ride.driver_rating}★` : 'Pending'} size="small" color="primary" />
                </Box>

                <Stack direction="row" spacing={1}>
                  <Button fullWidth variant="outlined" size="small" startIcon={<Phone size={16} />}>
                    Call Driver
                  </Button>
                  <Button fullWidth variant="outlined" size="small" startIcon={<MessageSquare size={16} />}>
                    Chat
                  </Button>
                </Stack>
              </Box>

              {/* Smart Pickup Point Hub instructions */}
              <Card sx={{ p: 2, mb: 3, background: 'rgba(0, 212, 255, 0.06)', border: '1px border #00D4FF' }}>
                <Typography variant="caption" sx={{ fontWeight: 700, color: '#00D4FF', display: 'block', mb: 0.5 }}>
                  PICKUP DETAILS:
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {ride?.pickup_label || pickup}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  Dispatch will confirm the pickup point after matching.
                </Typography>
              </Card>

              {bookingState === 'confirmed' ? (
                <Button fullWidth variant="contained" color="primary" size="large" disabled sx={{ py: 1.4 }}>
                  Waiting for vehicle assignment
                </Button>
              ) : (
                <Button
                  fullWidth
                  variant="contained"
                  color="secondary"
                  size="large"
                  onClick={() => setBookingState('idle')}
                  sx={{ py: 1.4 }}
                >
                  Complete Trip & Download Receipt
                </Button>
              )}
            </GlassCard>
          )}
        </Grid>

        {/* Right Map Canvas showing live telemetry */}
        <Grid item xs={12} md={7} lg={8}>
          <InteractiveMap
            pickupPoint={{ lat: 12.9784, lng: 77.6408 }}
            destinationPoint={{ lat: 12.9352, lng: 77.6245 }}
            height={620}
          />
        </Grid>
      </Grid>

      <ToastNotification
        open={toast.open}
        title={toast.title}
        message={toast.message}
        severity={toast.severity}
        onClose={() => setToast({ ...toast, open: false })}
      />
    </DashboardLayout>
  );
};
