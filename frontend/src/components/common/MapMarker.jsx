import React from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import { Car, Navigation, MapPin, Shield } from 'lucide-react';

export const MapMarker = ({
  type = 'vehicle', // vehicle | pickup | destination | stop
  title = '',
  status = 'active',
  speed = 0,
  onClick,
}) => {
  const getMarkerIcon = () => {
    switch (type) {
      case 'vehicle':
        return <Car size={20} color="#00D4FF" />;
      case 'pickup':
        return <MapPin size={22} color="#1E88E5" />;
      case 'destination':
        return <Navigation size={22} color="#EF4444" />;
      case 'stop':
        return <Shield size={20} color="#10B981" />;
      default:
        return <MapPin size={20} color="#00D4FF" />;
    }
  };

  const getBgGradient = () => {
    if (type === 'pickup') return 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)';
    if (type === 'destination') return 'linear-gradient(135deg, #EF4444 0%, #F59E0B 100%)';
    if (type === 'stop') return 'linear-gradient(135deg, #10B981 0%, #059669 100%)';
    return 'linear-gradient(135deg, #0B1F3A 0%, #1E88E5 100%)';
  };

  return (
    <Tooltip title={title || `${type.toUpperCase()} Marker`} arrow placement="top">
      <Box
        onClick={onClick}
        sx={{
          position: 'relative',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: 'translate(-50%, -50%)',
          transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translate(-50%, -50%) scale(1.18)',
            zIndex: 10,
          },
        }}
      >
        {/* Pulsing ring */}
        <Box
          className={status === 'active' ? 'vehicle-marker-pulse' : ''}
          sx={{
            position: 'absolute',
            width: 44,
            height: 44,
            borderRadius: '50%',
            backgroundColor: 'rgba(0, 212, 255, 0.2)',
          }}
        />

        {/* Inner Pin Container */}
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: getBgGradient(),
            border: '2px solid #FFFFFF',
            boxShadow: '0 4px 14px rgba(0, 0, 0, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFFFFF',
            zIndex: 2,
          }}
        >
          {getMarkerIcon()}
        </Box>

        {/* Speed or label badge */}
        {type === 'vehicle' && speed > 0 && (
          <Box
            sx={{
              position: 'absolute',
              bottom: -18,
              backgroundColor: '#0B1F3A',
              border: '1px solid #00D4FF',
              borderRadius: '10px',
              px: 0.8,
              py: 0.2,
              whiteSpace: 'nowrap',
            }}
          >
            <Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 700, fontSize: '0.68rem' }}>
              {speed} km/h
            </Typography>
          </Box>
        )}
      </Box>
    </Tooltip>
  );
};
