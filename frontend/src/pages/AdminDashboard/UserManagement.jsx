import React, { useState } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Chip,
  Button,
  InputAdornment,
  MenuItem,
  Select,
} from '@mui/material';
import { Search, User, Shield, Car } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';

const SAMPLE_USERS = [
  { id: 1, name: 'Aarav Mehta', email: 'aarav@example.com', role: 'passenger', status: 'active', totalRides: 28 },
  { id: 2, name: 'Rajesh Kumar', email: 'rajesh@smartroute.ai', role: 'driver', status: 'active', totalRides: 482 },
  { id: 3, name: 'Priya Sharma', email: 'priya@smartroute.ai', role: 'driver', status: 'active', totalRides: 390 },
  { id: 4, name: 'Ananya Deshmukh', email: 'ananya@example.com', role: 'passenger', status: 'active', totalRides: 14 },
  { id: 5, name: 'Admin Operations', email: 'admin@smartroute.ai', role: 'admin', status: 'active', totalRides: 0 },
];

export const UserManagement = () => {
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState(SAMPLE_USERS);

  const handleRoleChange = (userId, newRole) => {
    setUsers(users.map((u) => (u.id === userId ? { ...u, role: newRole } : u)));
  };

  const filteredUsers = users.filter((u) =>
    u.name.toLowerCase().includes(query.toLowerCase()) || u.email.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <DashboardLayout title="User & Driver Management">
      <GlassCard sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 800 }}>
            Registered Users ({users.length})
          </Typography>

          <TextField
            size="small"
            placeholder="Search users or drivers..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            InputProps={{
              startAdornment: <Search size={18} color="#94A3B8" style={{ marginRight: 8 }} />,
            }}
            sx={{ width: 300 }}
          />
        </Box>

        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>ID</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>User Name</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Email Address</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Assigned Role</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Total Rides</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredUsers.map((u) => (
              <TableRow key={u.id}>
                <TableCell sx={{ fontWeight: 700, color: '#00D4FF' }}>#{u.id}</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>{u.name}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>
                  <Select
                    size="small"
                    value={u.role}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    sx={{ height: 32, fontSize: '0.85rem', fontWeight: 700 }}
                  >
                    <MenuItem value="passenger">Passenger</MenuItem>
                    <MenuItem value="driver">Driver Partner</MenuItem>
                    <MenuItem value="admin">System Admin</MenuItem>
                  </Select>
                </TableCell>
                <TableCell><Chip label={u.status} color="success" size="small" /></TableCell>
                <TableCell sx={{ fontWeight: 700 }}>{u.totalRides}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </GlassCard>
    </DashboardLayout>
  );
};
