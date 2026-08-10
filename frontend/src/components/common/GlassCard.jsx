import React, { useContext } from 'react';
import { Card, CardContent } from '@mui/material';
import { motion } from 'framer-motion';
import { ColorModeContext } from '../../context/ColorModeContext';

const MotionCard = motion.create(Card);

export const GlassCard = ({
  children,
  hoverGlow = true,
  className = '',
  sx = {},
  onClick,
  initial = { opacity: 0, y: 20 },
  animate = { opacity: 1, y: 0 },
  transition = { duration: 0.5 },
  ...props
}) => {
  const { mode } = useContext(ColorModeContext);
  const isDark = mode === 'dark';

  return (
    <MotionCard
      initial={initial}
      animate={animate}
      transition={transition}
      whileHover={
        hoverGlow
          ? {
              y: -5,
              borderColor: 'rgba(0, 212, 255, 0.4)',
              boxShadow: isDark
                ? '0 12px 36px rgba(0, 212, 255, 0.25)'
                : '0 12px 36px rgba(30, 136, 229, 0.15)',
            }
          : {}
      }
      onClick={onClick}
      className={`${isDark ? 'glass-panel-dark' : 'glass-panel-light'} ${className}`}
      sx={{
        cursor: onClick ? 'pointer' : 'default',
        overflow: 'hidden',
        position: 'relative',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        ...sx,
      }}
      {...props}
    >
      <CardContent sx={{ p: { xs: 2.5, sm: 3 }, '&:last-child': { pb: { xs: 2.5, sm: 3 } } }}>
        {children}
      </CardContent>
    </MotionCard>
  );
};
