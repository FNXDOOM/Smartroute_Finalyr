import React, { useEffect, useState } from 'react';
import { Box, Typography, Stack, Card, Button, Alert } from '@mui/material';
import { Bell, Check } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { notificationsApi } from '../../services/api';

export const Notifications = () => {
  const [items, setItems] = useState([]); const [error, setError] = useState('');
  useEffect(() => { notificationsApi.list().then((d) => setItems(d.notifications || [])).catch((e) => setError(e.response?.data?.detail || 'Unable to load notifications.')); }, []);
  const markAll = async () => { await notificationsApi.markAllRead(); setItems((old) => old.map((n) => ({ ...n, is_read: true }))); };
  return <DashboardLayout title="Notifications & System Alerts"><GlassCard sx={{ p: 4, maxWidth: 800 }}><Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}><Typography variant="h6" sx={{ fontWeight: 800 }}>Notifications Feed</Typography><Button size="small" startIcon={<Check size={15} />} onClick={markAll}>Mark all read</Button></Box>{error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}<Stack spacing={2}>{items.map((n) => <Card key={n.id} sx={{ p: 2.5, borderRadius: 3, background: n.is_read ? 'rgba(255,255,255,.02)' : 'rgba(0,212,255,.06)' }}><Box sx={{ display: 'flex', gap: 2 }}><Bell size={20} color="#00D4FF" /><Box><Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{n.title}</Typography><Typography variant="body2" sx={{ color: 'text.secondary' }}>{n.message}</Typography><Typography variant="caption" sx={{ color: 'text.secondary' }}>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</Typography></Box></Box></Card>)}{!items.length && !error && <Typography color="text.secondary">No notifications yet.</Typography>}</Stack></GlassCard></DashboardLayout>;
};
