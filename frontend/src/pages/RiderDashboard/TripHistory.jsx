import React, { useState } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
} from '@mui/material';
import { Download, FileText, CheckCircle, Leaf } from 'lucide-react';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { GlassCard } from '../../components/common/GlassCard';
import { MOCK_TRIP_HISTORY } from '../../services/mockData';

export const TripHistory = () => {
  const [selectedReceipt, setSelectedReceipt] = useState(null);

  return (
    <DashboardLayout title="Trip History & Receipts">
      <GlassCard sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 800, mb: 3 }}>
          Past Rides & CO₂ Eco Receipts
        </Typography>

        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Trip ID</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Date & Time</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Route Summary</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Vehicle & Driver</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Flat Fare</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>CO₂ Saved</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Action</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {MOCK_TRIP_HISTORY.map((trip) => (
              <TableRow key={trip.id}>
                <TableCell sx={{ fontWeight: 700, color: '#00D4FF' }}>{trip.id}</TableCell>
                <TableCell>{trip.date}</TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{trip.pickup}</Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>→ {trip.destination}</Typography>
                </TableCell>
                <TableCell>{trip.driver}</TableCell>
                <TableCell sx={{ fontWeight: 800 }}>₹{trip.fare}</TableCell>
                <TableCell>
                  <Chip icon={<Leaf size={14} color="#10B981" />} label={`${trip.co2SavedKg} kg`} color="success" size="small" />
                </TableCell>
                <TableCell>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<FileText size={14} />}
                    onClick={() => setSelectedReceipt(trip)}
                  >
                    Receipt
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </GlassCard>

      {/* Download Receipt Modal Dialog */}
      <Dialog
        open={Boolean(selectedReceipt)}
        onClose={() => setSelectedReceipt(null)}
        PaperProps={{
          sx: {
            borderRadius: 4,
            p: 2,
            minWidth: 360,
            background: 'linear-gradient(135deg, #0B1F3A 0%, #1A2332 100%)',
            border: '1px solid rgba(0, 212, 255, 0.4)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 800, color: '#00D4FF' }}>
          SmartRoute AI — Official E-Receipt
        </DialogTitle>
        <DialogContent>
          {selectedReceipt && (
            <Box sx={{ pt: 1 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                RECEIPT #{selectedReceipt.id} • {selectedReceipt.date}
              </Typography>
              <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.1)' }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Pickup Point:</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>{selectedReceipt.pickup}</Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Destination:</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>{selectedReceipt.destination}</Typography>
              <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.1)' }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">AI Flat Fare Rate:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>₹{selectedReceipt.fare}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Surge Multiplier:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#10B981' }}>0.0x (GUARANTEED FLAT)</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2">Payment Method:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>{selectedReceipt.paymentMethod}</Typography>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button variant="contained" startIcon={<Download size={16} />} onClick={() => setSelectedReceipt(null)}>
            Download PDF
          </Button>
        </DialogActions>
      </Dialog>
    </DashboardLayout>
  );
};
