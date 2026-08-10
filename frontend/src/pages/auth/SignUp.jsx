import React, { useState, useContext } from 'react';
import { Box, Container, Typography, TextField, Button, ToggleButtonGroup, ToggleButton, InputAdornment, Alert } from '@mui/material';
import { User, Mail, Lock, Phone, Zap, ArrowRight, Car, UserCheck } from 'lucide-react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { GlassCard } from '../../components/common/GlassCard';
import { AuthContext } from '../../context/AuthContext';

export const SignUp = () => {
  const navigate = useNavigate();
  const { signup } = useContext(AuthContext);

  const [role, setRole] = useState('passenger'); // passenger | driver
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!name || !email || !password) {
      setError('Please fill in all required fields');
      return;
    }
    setSubmitting(true);
    // Proceed to OTP verification step
    navigate('/otp-verify', {
      state: { name, email, phone, password, role },
    });
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'radial-gradient(circle at 50% 30%, rgba(30, 136, 229, 0.18) 0%, #0B1F3A 75%, #121212 100%)',
        py: 6,
        px: 2,
      }}
    >
      <Container maxWidth="sm">
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Box
            component={RouterLink}
            to="/"
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 1.2,
              textDecoration: 'none',
              mb: 1.5,
            }}
          >
            <Box
              sx={{
                width: 44,
                height: 44,
                borderRadius: '14px',
                background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Zap size={26} color="#FFFFFF" />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#FFFFFF' }}>
              SmartRoute<span style={{ color: '#00D4FF' }}>.AI</span>
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Create an account for AI-grouped EV rides & flat fares.
          </Typography>
        </Box>

        <GlassCard sx={{ p: 4 }}>
          {error && <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>{error}</Alert>}

          {/* Role selector toggle */}
          <Box sx={{ mb: 3, textAlign: 'center' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', mb: 1 }}>
              SELECT ACCOUNT ROLE
            </Typography>
            <ToggleButtonGroup
              value={role}
              exclusive
              onChange={(e, val) => val && setRole(val)}
              fullWidth
              sx={{
                background: 'rgba(255, 255, 255, 0.05)',
                p: 0.5,
                borderRadius: 3,
                '& .MuiToggleButton-root': {
                  borderRadius: 2.5,
                  py: 1,
                  fontWeight: 700,
                  border: 'none',
                  color: 'text.secondary',
                  '&.Mui-selected': {
                    backgroundColor: '#1E88E5',
                    color: '#FFFFFF',
                  },
                },
              }}
            >
              <ToggleButton value="passenger">
                <UserCheck size={18} style={{ marginRight: 8 }} /> Rider / Passenger
              </ToggleButton>
              <ToggleButton value="driver">
                <Car size={18} style={{ marginRight: 8 }} /> EV Fleet Driver
              </ToggleButton>
            </ToggleButtonGroup>
          </Box>

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Full Name"
              variant="outlined"
              margin="normal"
              value={name}
              onChange={(e) => setName(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <User size={18} color="#1E88E5" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Email Address"
              type="email"
              variant="outlined"
              margin="normal"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Mail size={18} color="#00D4FF" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Phone Number"
              variant="outlined"
              margin="normal"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Phone size={18} color="#10B981" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Password"
              type="password"
              variant="outlined"
              margin="normal"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock size={18} color="#F59E0B" />
                  </InputAdornment>
                ),
              }}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={submitting}
              endIcon={<ArrowRight size={18} />}
              sx={{ py: 1.5, mt: 2, mb: 2 }}
            >
              Continue to OTP Verification
            </Button>
          </Box>

          <Box sx={{ textAlign: 'center', mt: 2 }}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Already have an account?{' '}
              <Typography
                component={RouterLink}
                to="/login"
                sx={{ color: '#00D4FF', fontWeight: 700, textDecoration: 'none' }}
              >
                Log In
              </Typography>
            </Typography>
          </Box>
        </GlassCard>
      </Container>
    </Box>
  );
};
