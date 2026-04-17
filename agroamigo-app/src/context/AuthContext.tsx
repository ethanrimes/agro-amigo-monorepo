import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { getSession, getProfile, onAuthStateChange, signOut as apiSignOut } from '../api/auth';

interface Profile {
  id: string;
  username: string;
  created_at: string;
}

interface AuthContextValue {
  userId: string | null;
  profile: Profile | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  userId: null,
  profile: null,
  loading: true,
  signOut: async () => {},
  refreshProfile: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (uid: string) => {
    try {
      const p = await getProfile(uid);
      setProfile(p);
    } catch {
      setProfile(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    if (userId) await loadProfile(userId);
  }, [userId, loadProfile]);

  useEffect(() => {
    let mounted = true;
    getSession().then(session => {
      if (!mounted) return;
      const uid = session?.user?.id || null;
      setUserId(uid);
      if (uid) loadProfile(uid);
      setLoading(false);
    }).catch(() => {
      if (mounted) setLoading(false);
    });

    const { data: { subscription } } = onAuthStateChange((_event, session) => {
      if (!mounted) return;
      const uid = session?.user?.id || null;
      setUserId(uid);
      if (uid) loadProfile(uid);
      else setProfile(null);
    });

    return () => { mounted = false; subscription.unsubscribe(); };
  }, [loadProfile]);

  const handleSignOut = useCallback(async () => {
    await apiSignOut();
    setUserId(null);
    setProfile(null);
  }, []);

  return (
    <AuthContext.Provider value={{ userId, profile, loading, signOut: handleSignOut, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
