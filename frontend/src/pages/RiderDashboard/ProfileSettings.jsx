import React, { useState, useContext } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  Grid,
  Avatar,
  Switch,
  FormControlLabel,
  Divider,
  Alert,
} from '@mui/material';
import { User, Mail, Phone, Home, Briefcase, Moon, Bell, Shield } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { AuthContext } from '../../context/AuthContext';
import { ColorModeContext } from '../../context/ColorModeContext';

export const ProfileSettings = () => {
  const { user, updateProfile } = useContext(AuthContext);
  const { mode, toggleColorMode } = useContext(ColorModeContext);

  const [name, setName] = useState(user?.name || 'Aarav Mehta');
  const [email, setEmail] = useState(user?.email || 'aarav.mehta@example.com');
  const [phone, setPhone] = useState(user?.phone || '+91 98765 43210');
  const [homeAddress, setHomeAddress] = useState('Indiranagar 100ft Road, Bengaluru');
  const [workAddress, setWorkAddress] = useState('Embassy TechVillage, Outer Ring Road');
  const [saved, setSaved] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    await updateProfile({ name, email, phone });
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <DashboardLayout title="Profile & Settings">
      <Grid container spacing={4} sx={{ maxWidth: 1000 }}>
        <Grid item xs={12} md={7}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Personal Information
            </Typography>

            {saved && <Alert severity="success" sx={{ mb: 2 }}>Profile updated successfully!</Alert>}

            <Box component="form" onSubmit={handleSave}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, mb: 4 }}>
                <Avatar sx={{ bgcolor: '#1E88E5', width: 72, height: 72, fontSize: '1.8rem', fontWeight: 800 }}>
                  {name[0]}
                </Avatar>
                <Button variant="outlined" size="small">Change Avatar</Button>
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <TextField fullWidth label="Full Name" value={name} onChange={(e) => setName(e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth label="Email Address" value={email} onChange={(e) => setEmail(e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth label="Phone Number" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </Grid>
                <Grid item xs={12}>
                  <Button variant="contained" type="submit" size="large" sx={{ mt: 2, py: 1.2 }}>
                    Save Profile Changes
                  </Button>
                </Grid>
              </Grid>
            </Box>

            <Divider sx={{ my: 4, borderColor: 'rgba(255,255,255,0.1)' }} />

            <Typography variant="h6" sx={{ fontWeight: 800, mb: 2 }}>
              Saved Places
            </Typography>

            <Stack spacing={2}>
              <TextField
                fullWidth
                label="Home Address"
                value={homeAddress}
                onChange={(e) => setHomeAddress(e.target.value)}
                InputProps={{
                  startAdornment: <Home size={18} color="#1E88E5" style={{ marginRight: 8 }} />,
                }}
              />
              <TextField
                fullWidth
                label="Work Address"
                value={workAddress}
                onChange={(e) => setWorkAddress(e.target.value)}
                InputProps={{
                  startAdornment: <Briefcase size={18} color="#00D4FF" style={{ marginRight: 8 }} />,
                }}
              />
            </Stack>
          </GlassCard>
        </Grid>

        <Grid item xs={12} md={5}>
          <GlassCard sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
              Preferences & Theme
            </Typography>

            <Stack spacing={3}>
              <FormControlLabel
                control={<Switch checked={mode === 'dark'} onChange={toggleColorMode} color="secondary" />}
                label={
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Dark Mode Theme</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>High contrast glassmorphic UI</Typography>
                  </Box>
                }
              />

              <FormControlLabel
                control={<Switch defaultChecked color="primary" />}
                label={
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Ride Push Notifications</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>Receive live ETA & vehicle updates</Typography>
                  </Box>
                }
              />

              <FormControlLabel
                control={<Switch defaultChecked color="primary" />}
                label={
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Eco Impact Summary</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>Monthly CO₂ savings report emails</Typography>
                  </Box>
                }
              />
            </Stack>
          </GlassCard>
        </Grid>
      </Grid>
    </DashboardLayout>
  );
};
