import React from 'react';
import { Box, Typography, Stack, Card, Chip, IconButton } from '@mui/material';
import { Bell, Zap, Leaf, Shield, Check } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';

const NOTIFS = [
  {
    id: 1,
    title: 'Ride Clustered & Confirmed',
    time: '10 mins ago',
    desc: 'Matched with 2 riders heading to Outer Ring Road. EV driver Tata Nexon is on the way.',
    icon: Zap,
    color: '#00D4FF',
    read: false,
  },
  {
    id: 2,
    title: 'Eco-Impact Milestone Reached!',
    time: '2 hours ago',
    desc: 'You have saved over 15kg of CO₂ emissions this month by using Smart AI Grouping.',
    icon: Leaf,
    color: '#10B981',
    read: false,
  },
  {
    id: 3,
    title: 'Flat Fare Assurance Active',
    time: '1 day ago',
    desc: 'Monsoon heavy rain reported. Your flat fare rates remain fixed with zero surge pricing.',
    icon: Shield,
    color: '#F59E0B',
    read: true,
  },
];

export const Notifications = () => {
  return (
    <DashboardLayout title="Notifications & System Alerts">
      <GlassCard sx={{ p: 4, maxWidth: 800 }}>
        <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
          Notifications Feed
        </Typography>

        <Stack spacing={2}>
          {NOTIFS.map((n) => {
            const Icon = n.icon;
            return (
              <Card
                key={n.id}
                sx={{
                  p: 2.5,
                  borderRadius: 3,
                  background: n.read ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 212, 255, 0.06)',
                  border: n.read ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(0, 212, 255, 0.3)',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 2,
                }}
              >
                <Box
                  sx={{
                    width: 42,
                    height: 42,
                    borderRadius: 3,
                    background: `linear-gradient(135deg, ${n.color}25 0%, rgba(11,31,58,0.5) 100%)`,
                    border: `1px solid ${n.color}50`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: n.color,
                    flexShrink: 0,
                  }}
                >
                  <Icon size={20} />
                </Box>
                <Box sx={{ flexGrow: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {n.title}
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                      {n.time}
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                    {n.desc}
                  </Typography>
                </Box>
              </Card>
            );
          })}
        </Stack>
      </GlassCard>
    </DashboardLayout>
  );
};
