import React, { useState, useEffect, useContext } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  IconButton,
  Box,
  Container,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Chip,
  useScrollTrigger,
} from '@mui/material';
import { Menu as MenuIcon, X as CloseIcon, Sun, Moon, Zap, Shield, User, LogOut } from 'lucide-react';
import { Link as RouterLink, useNavigate, useLocation } from 'react-router-dom';
import { ColorModeContext } from '../../context/ColorModeContext';
import { AuthContext } from '../../context/AuthContext';

export const Navbar = () => {
  const { mode, toggleColorMode } = useContext(ColorModeContext);
  const { isAuthenticated, user, logout } = useContext(AuthContext);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const trigger = useScrollTrigger({
    disableHysteresis: true,
    threshold: 20,
  });

  const isDark = mode === 'dark';

  const navLinks = [
    { label: 'Home', path: '/' },
    { label: 'About', path: '/about' },
    { label: 'Features', path: '/features' },
    { label: 'How It Works', path: '/how-it-works' },
    { label: 'Pricing', path: '/pricing' },
    { label: 'Contact', path: '/contact' },
  ];

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const getDashboardPath = () => {
    if (user?.role === 'driver') return '/driver-dashboard';
    if (user?.role === 'admin') return '/admin-dashboard';
    return '/rider-dashboard';
  };

  return (
    <AppBar
      position="sticky"
      elevation={trigger ? 4 : 0}
      sx={{
        backgroundColor: trigger
          ? isDark
            ? 'rgba(11, 31, 58, 0.88)'
            : 'rgba(255, 255, 255, 0.92)'
          : 'transparent',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: trigger
          ? isDark
            ? '1px solid rgba(255, 255, 255, 0.1)'
            : '1px solid rgba(226, 232, 240, 0.8)'
          : 'none',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      <Container maxWidth="xl">
        <Toolbar disableGutters sx={{ justifyContent: 'space-between', py: 1 }}>
          {/* Logo */}
          <Box
            component={RouterLink}
            to="/"
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.2,
              textDecoration: 'none',
              color: 'inherit',
            }}
          >
            <Box
              sx={{
                width: 42,
                height: 42,
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 16px rgba(0, 212, 255, 0.4)',
              }}
            >
              <Zap size={24} color="#FFFFFF" />
            </Box>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 800,
                letterSpacing: '-0.02em',
                background: 'linear-gradient(90deg, #FFFFFF 0%, #00D4FF 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: isDark ? 'transparent' : 'inherit',
              }}
            >
              SmartRoute<span style={{ color: '#00D4FF' }}>.AI</span>
            </Typography>
          </Box>

          {/* Desktop Nav Links */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 1 }}>
            {navLinks.map((link) => {
              const active = location.pathname === link.path;
              return (
                <Button
                  key={link.label}
                  component={RouterLink}
                  to={link.path}
                  sx={{
                    color: active ? '#00D4FF' : 'text.primary',
                    fontWeight: active ? 700 : 500,
                    px: 2,
                    py: 1,
                    borderRadius: 2,
                    position: 'relative',
                    '&:hover': {
                      color: '#00D4FF',
                      backgroundColor: 'rgba(0, 212, 255, 0.06)',
                    },
                  }}
                >
                  {link.label}
                </Button>
              );
            })}
          </Box>

          {/* Right Action buttons */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {/* Dark mode toggle */}
            <IconButton onClick={toggleColorMode} color="inherit" sx={{ border: '1px solid rgba(255,255,255,0.1)' }}>
              {isDark ? <Sun size={20} color="#F59E0B" /> : <Moon size={20} color="#1E88E5" />}
            </IconButton>

            {isAuthenticated ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={() => navigate(getDashboardPath())}
                  startIcon={<User size={18} />}
                >
                  Dashboard ({user?.role?.toUpperCase()})
                </Button>
                <IconButton onClick={logout} color="error" title="Logout">
                  <LogOut size={20} />
                </IconButton>
              </Box>
            ) : (
              <Box sx={{ display: { xs: 'none', sm: 'flex' }, gap: 1 }}>
                <Button variant="outlined" color="primary" component={RouterLink} to="/login">
                  Log In
                </Button>
                <Button variant="contained" color="primary" component={RouterLink} to="/signup">
                  Sign Up Free
                </Button>
              </Box>
            )}

            {/* Mobile menu hamburger button */}
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleDrawerToggle}
              sx={{ display: { md: 'none' } }}
            >
              <MenuIcon size={26} />
            </IconButton>
          </Box>
        </Toolbar>
      </Container>

      {/* Mobile Drawer */}
      <Drawer
        anchor="right"
        open={mobileOpen}
        onClose={handleDrawerToggle}
        ModalProps={{ keepMounted: true }}
        PaperProps={{
          sx: {
            width: 280,
            background: isDark ? '#0B1F3A' : '#FFFFFF',
            p: 3,
          },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 800, color: '#00D4FF' }}>
            SmartRoute AI
          </Typography>
          <IconButton onClick={handleDrawerToggle} color="inherit">
            <CloseIcon size={22} />
          </IconButton>
        </Box>

        <List sx={{ mb: 2 }}>
          {navLinks.map((link) => (
            <ListItem key={link.label} disablePadding sx={{ mb: 1 }}>
              <ListItemButton
                component={RouterLink}
                to={link.path}
                onClick={handleDrawerToggle}
                sx={{ borderRadius: 2 }}
              >
                <ListItemText primary={link.label} primaryTypographyProps={{ fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>

        {!isAuthenticated && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mt: 'auto' }}>
            <Button variant="outlined" fullWidth component={RouterLink} to="/login" onClick={handleDrawerToggle}>
              Log In
            </Button>
            <Button variant="contained" fullWidth component={RouterLink} to="/signup" onClick={handleDrawerToggle}>
              Sign Up
            </Button>
          </Box>
        )}
      </Drawer>
    </AppBar>
  );
};
