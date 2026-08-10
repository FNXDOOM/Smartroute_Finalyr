import React from 'react';
import { Skeleton, Box, Card, CardContent } from '@mui/material';

export const DashboardCardSkeleton = () => (
  <Card sx={{ borderRadius: 4, p: 1 }}>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Skeleton variant="circular" width={40} height={40} />
        <Skeleton variant="rounded" width={60} height={24} />
      </Box>
      <Skeleton variant="text" width="40%" height={24} sx={{ mb: 1 }} />
      <Skeleton variant="text" width="70%" height={40} sx={{ mb: 2 }} />
      <Skeleton variant="rounded" width="100%" height={8} />
    </CardContent>
  </Card>
);

export const MapLoadingSkeleton = () => (
  <Box
    className="skeleton-shimmer"
    sx={{
      width: '100%',
      height: '100%',
      minHeight: 400,
      borderRadius: 4,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'text.secondary',
    }}
  >
    <Box sx={{ textAlign: 'center' }}>
      <Skeleton variant="circular" width={60} height={60} sx={{ mx: 'auto', mb: 2 }} />
      <Skeleton variant="text" width={200} height={30} sx={{ mx: 'auto' }} />
    </Box>
  </Box>
);
