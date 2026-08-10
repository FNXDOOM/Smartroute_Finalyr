import React, { useState, useEffect, useRef, useContext } from 'react';
import { Box, Container, Typography, Button, TextField, Alert, Stack } from '@mui/material';
import { ShieldCheck, ArrowRight, RefreshCw, Zap } from 'lucide-react';
import { useLocation, useNavigate, Link as RouterLink } from 'react-router-dom';
import { GlassCard } from '../../components/common/GlassCard';
import { AuthContext } from '../../context/AuthContext';

export const OTPVerification = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { signup } = useContext(AuthContext);

  const signupData = location.state || {};
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [timer, setTimer] = useState(30);
  const [error, setError] = useState('');
  const [verifying, setVerifying] = useState(false);
  const inputRefs = useRef([]);

  useEffect(() => {
    const interval = setInterval(() => {
      setTimer((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleChange = (index, value) => {
    if (isNaN(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value.substring(value.length - 1);
    setOtp(newOtp);

    // Auto-focus next input
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleVerify = async () => {
    setError('');
    const otpCode = otp.join('');
    if (otpCode.length < 6) {
      setError('Please enter the complete 6-digit OTP code');
      return;
    }
    setVerifying(true);

    // Call backend signup or demo signup
    const res = await signup(signupData);
    setVerifying(false);

    if (res.success) {
      if (signupData.role === 'driver') navigate('/driver-dashboard');
      else navigate('/rider-dashboard');
    }
  };

  const handleResend = () => {
    setTimer(30);
    setOtp(['', '', '', '', '', '']);
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
            sx={{
              width: 50,
              height: 50,
              borderRadius: '16px',
              background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              mx: 'auto',
              mb: 2,
            }}
          >
            <ShieldCheck size={28} color="#FFFFFF" />
          </Box>
          <Typography variant="h5" sx={{ fontWeight: 800 }}>
            Enter OTP Code
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            We sent a 6-digit security code to{' '}
            <strong style={{ color: '#00D4FF' }}>{signupData.email || 'your phone/email'}</strong>
          </Typography>
        </Box>

        <GlassCard sx={{ p: 4, textAlign: 'center' }}>
          {error && <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>{error}</Alert>}

          <Stack direction="row" spacing={1} justifyContent="center" sx={{ mb: 3 }}>
            {otp.map((digit, index) => (
              <TextField
                key={index}
                inputRef={(el) => (inputRefs.current[index] = el)}
                value={digit}
                onChange={(e) => handleChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                inputProps={{
                  maxLength: 1,
                  style: { textAlign: 'center', fontSize: '1.4rem', fontWeight: 800, padding: '12px 0' },
                }}
                sx={{ width: 44 }}
              />
            ))}
          </Stack>

          <Button
            fullWidth
            variant="contained"
            size="large"
            onClick={handleVerify}
            disabled={verifying}
            endIcon={<ArrowRight size={18} />}
            sx={{ py: 1.4, mb: 2 }}
          >
            {verifying ? 'Verifying...' : 'Verify & Continue'}
          </Button>

          <Box sx={{ mt: 2 }}>
            {timer > 0 ? (
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Resend code in <strong style={{ color: '#00D4FF' }}>{timer}s</strong>
              </Typography>
            ) : (
              <Button
                variant="text"
                size="small"
                onClick={handleResend}
                startIcon={<RefreshCw size={16} />}
                sx={{ color: '#00D4FF' }}
              >
                Resend OTP Code
              </Button>
            )}
          </Box>
        </GlassCard>
      </Container>
    </Box>
  );
};
