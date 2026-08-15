import { createContext, useEffect, useState } from 'react';
import { useAuth, useClerk, useUser } from '@clerk/clerk-react';
import { authApi, setAuthTokenGetter } from '../services/api';

export const AuthContext = createContext({
  user: null,
  token: null,
  isAuthenticated: false,
  role: 'passenger', // passenger | driver | admin
  logout: () => {},
  updateProfile: async () => {},
  loading: true,
});

export const AuthProvider = ({ children }) => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAuthTokenGetter(getToken);
    return () => setAuthTokenGetter(null);
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn || !clerkUser) {
      setUser(null);
      setToken(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const syncUser = async () => {
      try {
        const sessionToken = await getToken();
        setToken(sessionToken);
        const profile = await authApi.getProfile();
        if (!cancelled) {
          setUser(profile || {
            id: clerkUser.id,
            name: clerkUser.fullName || clerkUser.firstName || 'Smart Rider',
            email: clerkUser.primaryEmailAddress?.emailAddress || '',
            role: clerkUser.publicMetadata?.role || 'passenger',
            phone: clerkUser.primaryPhoneNumber?.phoneNumber || '',
          });
        }
      } catch (error) {
        if (!cancelled) setUser(null);
        console.error('Could not load the backend profile:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    syncUser();
    return () => { cancelled = true; };
  }, [getToken, isLoaded, isSignedIn, clerkUser]);

  const logout = () => signOut();

  const updateProfile = async (updatedFields) => {
    const updated = await authApi.updateProfile(updatedFields);
    setUser(updated);
    return updated;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: Boolean(isSignedIn && user),
        role: user?.role || 'passenger',
        logout,
        updateProfile,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
