import { createTheme } from '@mui/material/styles';
import { BRAND_COLORS, GRADIENTS } from './palette';

export const getCustomTheme = (mode = 'dark') => {
  const isDark = mode === 'dark';

  return createTheme({
    palette: {
      mode,
      primary: {
        main: BRAND_COLORS.electricBlue,
        dark: BRAND_COLORS.navy,
        light: BRAND_COLORS.cyan,
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: BRAND_COLORS.cyan,
        dark: '#00B8E6',
        light: '#80EAFF',
        contrastText: BRAND_COLORS.navy,
      },
      background: {
        default: isDark ? BRAND_COLORS.darkBg : BRAND_COLORS.lightBg,
        paper: isDark ? BRAND_COLORS.darkSurface : BRAND_COLORS.lightSurface,
        navy: BRAND_COLORS.navy,
      },
      text: {
        primary: isDark ? BRAND_COLORS.textPrimaryDark : BRAND_COLORS.textPrimaryLight,
        secondary: isDark ? BRAND_COLORS.textSecondaryDark : BRAND_COLORS.textSecondaryLight,
      },
      success: { main: BRAND_COLORS.success },
      warning: { main: BRAND_COLORS.warning },
      error: { main: BRAND_COLORS.error },
      info: { main: BRAND_COLORS.info },
      divider: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(15, 23, 42, 0.12)',
    },
    typography: {
      fontFamily: ['Inter', 'Poppins', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'].join(','),
      h1: {
        fontWeight: 800,
        fontSize: '3.2rem',
        lineHeight: 1.15,
        letterSpacing: '-0.02em',
      },
      h2: {
        fontWeight: 700,
        fontSize: '2.4rem',
        lineHeight: 1.25,
        letterSpacing: '-0.01em',
      },
      h3: {
        fontWeight: 700,
        fontSize: '1.85rem',
        lineHeight: 1.3,
      },
      h4: {
        fontWeight: 600,
        fontSize: '1.45rem',
        lineHeight: 1.35,
      },
      h5: {
        fontWeight: 600,
        fontSize: '1.2rem',
      },
      h6: {
        fontWeight: 600,
        fontSize: '1rem',
      },
      button: {
        textTransform: 'none',
        fontWeight: 600,
        letterSpacing: '0.01em',
      },
    },
    shape: {
      borderRadius: 16,
    },
    shadows: [
      'none',
      isDark ? '0 2px 8px rgba(0, 0, 0, 0.4)' : '0 2px 8px rgba(15, 23, 42, 0.06)',
      isDark ? '0 4px 16px rgba(0, 0, 0, 0.5)' : '0 4px 16px rgba(15, 23, 42, 0.08)',
      isDark ? '0 8px 24px rgba(0, 0, 0, 0.6)' : '0 8px 24px rgba(15, 23, 42, 0.1)',
      isDark ? '0 12px 32px rgba(0, 0, 0, 0.7)' : '0 12px 32px rgba(15, 23, 42, 0.12)',
      isDark ? '0 16px 48px rgba(0, 0, 0, 0.8)' : '0 16px 48px rgba(15, 23, 42, 0.14)',
      ...Array(19).fill(isDark ? '0 20px 60px rgba(0, 0, 0, 0.9)' : '0 20px 60px rgba(15, 23, 42, 0.15)'),
    ],
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: isDark ? BRAND_COLORS.darkBg : BRAND_COLORS.lightBg,
            color: isDark ? BRAND_COLORS.textPrimaryDark : BRAND_COLORS.textPrimaryLight,
            overflowX: 'hidden',
            scrollBehavior: 'smooth',
          },
          '::selection': {
            backgroundColor: BRAND_COLORS.cyan,
            color: BRAND_COLORS.navy,
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            padding: '10px 24px',
            fontSize: '0.95rem',
            transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': {
              transform: 'translateY(-2px)',
              boxShadow: '0 8px 20px rgba(30, 136, 229, 0.35)',
            },
          },
          containedPrimary: {
            background: GRADIENTS.accentGlow,
            color: '#FFFFFF',
            fontWeight: 700,
            '&:hover': {
              background: 'linear-gradient(90deg, #1565C0 0%, #00B8E6 100%)',
            },
          },
          outlinedPrimary: {
            borderColor: BRAND_COLORS.cyan,
            color: BRAND_COLORS.cyan,
            borderWidth: 1.5,
            '&:hover': {
              borderWidth: 1.5,
              borderColor: BRAND_COLORS.cyanHover,
              backgroundColor: 'rgba(0, 212, 255, 0.08)',
            },
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 20,
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            background: isDark ? GRADIENTS.glassDark : GRADIENTS.glassLight,
            border: isDark ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(226, 232, 240, 0.8)',
            transition: 'transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease',
          },
        },
      },
      MuiAccordion: {
        styleOverrides: {
          root: {
            borderRadius: '16px !important',
            marginBottom: 12,
            background: isDark ? BRAND_COLORS.darkSurface : BRAND_COLORS.lightSurface,
            border: isDark ? '1px solid rgba(255, 255, 255, 0.08)' : '1px solid rgba(226, 232, 240, 0.8)',
            boxShadow: 'none',
            '&:before': { display: 'none' },
            '&.Mui-expanded': {
              borderColor: BRAND_COLORS.cyan,
              boxShadow: '0 4px 20px rgba(0, 212, 255, 0.15)',
            },
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            fontWeight: 600,
            borderRadius: 8,
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 12,
              '& fieldset': {
                borderColor: isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.15)',
              },
              '&:hover fieldset': {
                borderColor: BRAND_COLORS.cyan,
              },
              '&.Mui-focused fieldset': {
                borderColor: BRAND_COLORS.cyan,
                borderWidth: 2,
              },
            },
          },
        },
      },
    },
  });
};
