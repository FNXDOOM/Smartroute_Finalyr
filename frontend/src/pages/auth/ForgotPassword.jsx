import React, { useState } from 'react';
import { Box, Container, Typography, TextField, Button, Alert, InputAdornment } from '@mui/material';
import { Mail, Lock, ArrowRight, ShieldCheck } from 'lucide-react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { GlassCard } from '../../components/common/GlassCard';

export const ForgotPassword = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: enter email, 2: enter new password
  const [email, setEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleSendReset = (e) => {
    e.preventDefault();
    if (!email) return;
    setStep(2);
  };

  const handleResetPassword = (e) => {
    e.preventDefault();
    if (!newPassword) return;
    setSuccessMsg('Password reset successfully! Redirecting to login...');
    setTimeout(() => {
      navigate('/login');
    }, 2000);
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
          <Typography variant="h5" sx={{ fontWeight: 800 }}>
            Reset Password
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            {step === 1 ? 'Enter your registered email address to receive reset instructions.' : 'Enter your new account password.'}
          </Typography>
        </Box>

        <GlassCard sx={{ p: 4 }}>
          {successMsg && <Alert severity="success" sx={{ mb: 2 }}>{successMsg}</Alert>}

          {step === 1 ? (
            <Box component="form" onSubmit={handleSendReset}>
              <TextField
                fullWidth
                label="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                margin="normal"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Mail size={18} color="#00D4FF" />
                    </InputAdornment>
                  ),
                }}
              />
              <Button fullWidth variant="contained" type="submit" size="large" sx={{ mt: 2, py: 1.4 }}>
                Send Reset Code
              </Button>
            </Box>
          ) : (
            <Box component="form" onSubmit={handleResetPassword}>
              <TextField
                fullWidth
                label="New Password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                margin="normal"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Lock size={18} color="#10B981" />
                    </InputAdornment>
                  ),
                }}
              />
              <Button fullWidth variant="contained" type="submit" size="large" sx={{ mt: 2, py: 1.4 }}>
                Update Password
              </Button>
            </Box>
          )}

          <Box sx={{ textAlign: 'center', mt: 3 }}>
            <Typography variant="caption" component={RouterLink} to="/login" sx={{ color: '#00D4FF', textDecoration: 'none', fontWeight: 700 }}>
              Back to Login
            </Typography>
          </Box>
        </GlassCard>
      </Container>
    </Box>
  );
};
