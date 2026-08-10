import React from 'react';
import { Snackbar, Alert, AlertTitle } from '@mui/material';

export const ToastNotification = ({
  open,
  onClose,
  severity = 'info', // success | info | warning | error
  title = '',
  message = '',
  autoHideDuration = 4000,
}) => {
  return (
    <Snackbar
      open={open}
      autoHideDuration={autoHideDuration}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
    >
      <Alert
        onClose={onClose}
        severity={severity}
        variant="filled"
        sx={{
          width: '100%',
          borderRadius: 3,
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
          fontWeight: 600,
          '& .MuiAlert-icon': {
            alignItems: 'center',
          },
        }}
      >
        {title && <AlertTitle sx={{ fontWeight: 700 }}>{title}</AlertTitle>}
        {message}
      </Alert>
    </Snackbar>
  );
};
