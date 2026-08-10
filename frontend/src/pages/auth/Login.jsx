import React, { useState, useContext } from 'react';
import { Box, Container, Typography, TextField, Button, Divider, InputAdornment, Alert, IconButton } from '@mui/material';
import { Mail, Lock, Eye, EyeOff, Zap, ArrowRight } from 'lucide-react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { GlassCard } from '../../components/common/GlassCard';
import { AuthContext } from '../../context/AuthContext';

export const Login = () => {
  const navigate = useNavigate();
  const { login } = useContext(AuthContext);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('Please fill in both email and password');
      return;
    }
    setSubmitting(true);
    const res = await login(email, password);
    setSubmitting(false);

    if (res.success) {
      // Redirect based on role
      if (res.user.role === 'driver') navigate('/driver-dashboard');
      else if (res.user.role === 'admin') navigate('/admin-dashboard');
      else navigate('/rider-dashboard');
    }
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
      <Container maxWidth="xs">
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
            Welcome back! Log in to access your AI-optimized rides.
          </Typography>
        </Box>

        <GlassCard sx={{ p: 4 }}>
          {error && <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>{error}</Alert>}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Email Address or Phone"
              variant="outlined"
              margin="normal"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Mail size={18} color="#1E88E5" />
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              variant="outlined"
              margin="normal"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock size={18} color="#00D4FF" />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPassword(!showPassword)} edge="end">
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1, mb: 2 }}>
              <Typography
                variant="caption"
                component={RouterLink}
                to="/forgot-password"
                sx={{ color: '#00D4FF', textDecoration: 'none', fontWeight: 600 }}
              >
                Forgot Password?
              </Typography>
            </Box>

            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={submitting}
              endIcon={<ArrowRight size={18} />}
              sx={{ py: 1.4, mb: 2 }}
            >
              {submitting ? 'Authenticating...' : 'Sign In'}
            </Button>
          </Box>

          <Divider sx={{ my: 2.5, color: 'text.secondary', fontSize: '0.8rem' }}>OR</Divider>

          <Button
            fullWidth
            variant="outlined"
            onClick={() => login('google.user@smartroute.ai', 'google_pass')}
            sx={{
              py: 1.2,
              borderColor: 'rgba(255, 255, 255, 0.2)',
              color: 'text.primary',
              '&:hover': { borderColor: '#00D4FF' },
            }}
          >
            Continue with Google
          </Button>

          <Box sx={{ textAlign: 'center', mt: 3 }}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Don't have an account?{' '}
              <Typography
                component={RouterLink}
                to="/signup"
                sx={{ color: '#00D4FF', fontWeight: 700, textDecoration: 'none' }}
              >
                Sign Up Free
              </Typography>
            </Typography>
          </Box>
        </GlassCard>
      </Container>
    </Box>
  );
};
