import React, { useState, useContext } from 'react';
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Avatar,
  Menu,
  MenuItem,
  Divider,
  Badge,
  Chip,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Zap,
  MapPin,
  Car,
  PieChart,
  History,
  CreditCard,
  Bell,
  User,
  Settings,
  LogOut,
  Sun,
  Moon,
  Activity,
  Users,
  TrendingUp,
} from 'lucide-react';
import { Link as RouterLink, useNavigate, useLocation } from 'react-router-dom';
import { ColorModeContext } from '../../context/ColorModeContext';
import { AuthContext } from '../../context/AuthContext';

const DRAWER_WIDTH = 260;

export const DashboardLayout = ({ children, title = 'Dashboard' }) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, toggleColorMode } = useContext(ColorModeContext);
  const { user, logout, role } = useContext(AuthContext);

  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);

  const isDark = mode === 'dark';

  const handleDrawerToggle = () => setMobileOpen(!mobileOpen);
  const handleMenuOpen = (e) => setAnchorEl(e.currentTarget);
  const handleMenuClose = () => setAnchorEl(null);

  const handleLogout = () => {
    handleMenuClose();
    logout();
    navigate('/login');
  };

  // Nav menus according to role
  const riderMenu = [
    { label: 'Book & Track Ride', path: '/rider-dashboard', icon: MapPin },
    { label: 'Trip History', path: '/rider-dashboard/history', icon: History },
    { label: 'Payment Methods', path: '/rider-dashboard/payments', icon: CreditCard },
    { label: 'Notifications', path: '/rider-dashboard/notifications', icon: Bell },
    { label: 'Profile & Saved Places', path: '/rider-dashboard/profile', icon: User },
  ];

  const driverMenu = [
    { label: 'Live Trip & Queue', path: '/driver-dashboard', icon: Car },
    { label: 'Earnings Summary', path: '/driver-dashboard/earnings', icon: TrendingUp },
    { label: 'Performance & Rating', path: '/driver-dashboard/performance', icon: Activity },
  ];

  const adminMenu = [
    { label: 'Overview & Demand Map', path: '/admin-dashboard', icon: PieChart },
    { label: 'Live Fleet Tracking', path: '/admin-dashboard/fleet', icon: Car },
    { label: 'AI Analytics & CO2', path: '/admin-dashboard/analytics', icon: TrendingUp },
    { label: 'User Management', path: '/admin-dashboard/users', icon: Users },
  ];

  const currentNavItems = role === 'driver' ? driverMenu : role === 'admin' ? adminMenu : riderMenu;

  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 2 }}>
      {/* Brand Header */}
      <Box
        component={RouterLink}
        to="/"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.2,
          textDecoration: 'none',
          color: 'inherit',
          p: 1.5,
          mb: 2,
        }}
      >
        <Box
          sx={{
            width: 38,
            height: 38,
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #1E88E5 0%, #00D4FF 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Zap size={22} color="#FFFFFF" />
        </Box>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1.1 }}>
            SmartRoute<span style={{ color: '#00D4FF' }}>.AI</span>
          </Typography>
          <Chip
            label={role ? role.toUpperCase() : 'RIDER'}
            size="small"
            color={role === 'admin' ? 'secondary' : role === 'driver' ? 'info' : 'primary'}
            sx={{ height: 18, fontSize: '0.62rem', fontWeight: 800, mt: 0.3 }}
          />
        </Box>
      </Box>

      <Divider sx={{ mb: 2, borderColor: 'divider' }} />

      {/* Navigation Links */}
      <List sx={{ flexGrow: 1 }}>
        {currentNavItems.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path;
          return (
            <ListItem key={item.label} disablePadding sx={{ mb: 1 }}>
              <ListItemButton
                component={RouterLink}
                to={item.path}
                onClick={() => setMobileOpen(false)}
                sx={{
                  borderRadius: 3,
                  py: 1.2,
                  backgroundColor: active
                    ? isDark
                      ? 'rgba(0, 212, 255, 0.12)'
                      : 'rgba(30, 136, 229, 0.1)'
                    : 'transparent',
                  border: active ? '1px solid rgba(0, 212, 255, 0.3)' : '1px solid transparent',
                  color: active ? '#00D4FF' : 'text.primary',
                  '&:hover': {
                    backgroundColor: 'rgba(0, 212, 255, 0.08)',
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: active ? '#00D4FF' : 'text.secondary' }}>
                  <Icon size={20} />
                </ListItemIcon>
                <ListItemText
                  primary={item.label}
                  primaryTypographyProps={{ fontSize: '0.9rem', fontWeight: active ? 700 : 500 }}
                />
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>

      {/* User profile bottom card */}
      <Box
        sx={{
          p: 2,
          borderRadius: 3,
          background: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
          <Avatar sx={{ bgcolor: '#1E88E5', width: 36, height: 36, fontWeight: 700 }}>
            {user?.name ? user.name[0].toUpperCase() : 'U'}
          </Avatar>
          <Box sx={{ overflow: 'hidden' }}>
            <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>
              {user?.name || 'Smart Rider'}
            </Typography>
            <Typography variant="caption" noWrap sx={{ color: 'text.secondary', display: 'block' }}>
              {user?.email || 'user@smartroute.ai'}
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: 'background.default' }}>
      {/* AppBar Header */}
      <AppBar
        position="fixed"
        sx={{
          width: { lg: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { lg: `${DRAWER_WIDTH}px` },
          backgroundColor: isDark ? 'rgba(18, 18, 18, 0.85)' : 'rgba(255, 255, 255, 0.85)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid',
          borderColor: 'divider',
          boxShadow: 'none',
          color: 'text.primary',
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <IconButton color="inherit" edge="start" onClick={handleDrawerToggle} sx={{ mr: 1, display: { lg: 'none' } }}>
              <MenuIcon size={24} />
            </IconButton>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {title}
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <IconButton onClick={toggleColorMode} color="inherit">
              {isDark ? <Sun size={20} color="#F59E0B" /> : <Moon size={20} color="#1E88E5" />}
            </IconButton>

            <IconButton color="inherit" component={RouterLink} to="/rider-dashboard/notifications">
              <Badge badgeContent={3} color="primary">
                <Bell size={20} />
              </Badge>
            </IconButton>

            <IconButton onClick={handleMenuOpen} sx={{ p: 0.5 }}>
              <Avatar sx={{ bgcolor: '#00D4FF', color: '#0B1F3A', width: 34, height: 34, fontWeight: 800 }}>
                {user?.name ? user.name[0].toUpperCase() : 'S'}
              </Avatar>
            </IconButton>

            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
              PaperProps={{
                sx: {
                  mt: 1.5,
                  minWidth: 180,
                  borderRadius: 3,
                  border: '1px solid rgba(255,255,255,0.1)',
                },
              }}
            >
              <MenuItem component={RouterLink} to="/rider-dashboard/profile" onClick={handleMenuClose}>
                <ListItemIcon><User size={18} /></ListItemIcon> Profile Settings
              </MenuItem>
              <Divider />
              <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
                <ListItemIcon><LogOut size={18} color="#EF4444" /></ListItemIcon> Logout
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Drawer */}
      <Box component="nav" sx={{ width: { lg: DRAWER_WIDTH }, flexShrink: { lg: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          PaperProps={{ sx: { width: DRAWER_WIDTH, background: isDark ? '#0B1F3A' : '#FFFFFF' } }}
        >
          {drawerContent}
        </Drawer>
        <Drawer
          variant="permanent"
          PaperProps={{ sx: { width: DRAWER_WIDTH, background: isDark ? '#0B1F3A' : '#FFFFFF', borderRight: '1px solid', borderColor: 'divider' } }}
          sx={{ display: { xs: 'none', lg: 'block' } }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      {/* Main Content Area */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2.5, sm: 4 },
          width: { lg: `calc(100% - ${DRAWER_WIDTH}px)` },
          mt: 8,
          minHeight: 'calc(100vh - 64px)',
        }}
      >
        {children}
      </Box>
    </Box>
  );
};
