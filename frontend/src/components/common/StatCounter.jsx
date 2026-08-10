import React, { useEffect, useState } from 'react';
import { Typography, Box } from '@mui/material';
import { motion, useMotionValue, animate } from 'framer-motion';

export const StatCounter = ({
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  duration = 2.5,
  label = '',
  icon: Icon,
}) => {
  const count = useMotionValue(0);
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    const numericValue = typeof value === 'number' ? value : parseFloat(value) || 0;
    const controls = animate(count, numericValue, {
      duration,
      onUpdate: (latest) => {
        setDisplayValue(latest.toFixed(decimals));
      },
    });

    return () => controls.stop();
  }, [value, duration, decimals, count]);

  return (
    <Box sx={{ textAlign: 'center', p: 2 }}>
      {Icon && (
        <Box
          sx={{
            width: 54,
            height: 54,
            borderRadius: '16px',
            background: 'linear-gradient(135deg, rgba(30, 136, 229, 0.2) 0%, rgba(0, 212, 255, 0.1) 100%)',
            border: '1px solid rgba(0, 212, 255, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 1.5,
            color: '#00D4FF',
          }}
        >
          <Icon size={28} />
        </Box>
      )}
      <Typography
        variant="h2"
        sx={{
          fontWeight: 800,
          background: 'linear-gradient(135deg, #FFFFFF 0%, #1E88E5 50%, #00D4FF 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          mb: 0.5,
          fontSize: { xs: '2rem', sm: '2.5rem' },
        }}
      >
        {prefix}
        {Number(displayValue).toLocaleString()}
        {suffix}
      </Typography>
      {label && (
        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 500 }}>
          {label}
        </Typography>
      )}
    </Box>
  );
};
