'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { IoPersonOutline, IoMailOutline, IoLockClosedOutline, IoLogIn } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize } from '@agroamigo/shared';
import { signUp, signIn } from '@agroamigo/shared/api/auth';
import { useAuth } from '@/context/AuthContext';
import { useLanguage } from '@/context/LanguageContext';

export default function AuthPage() {
  const router = useRouter();
  const { userId, profile, signOut } = useAuth();
  const { t } = useLanguage();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');

  if (userId && profile) {
    return (
      <div style={{ padding: spacing.lg, paddingBottom: 40 }}>
        <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary, marginBottom: spacing.md }}>{t.auth_account}</h2>
        <div style={{
          backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.lg,
          border: `1px solid ${colors.borderLight}`, marginBottom: spacing.lg,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md }}>
            <div style={{ width: 48, height: 48, borderRadius: borderRadius.full, backgroundColor: colors.primary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <IoPersonOutline size={24} color={colors.primary} />
            </div>
            <div>
              <div style={{ fontSize: fontSize.lg, fontWeight: 700, color: colors.text.primary }}>{profile.username}</div>
              <div style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>{t.auth_member_since} {new Date(profile.created_at).toLocaleDateString()}</div>
            </div>
          </div>
          <button onClick={async () => { await signOut(); }} style={{
            width: '100%', padding: `${spacing.md}px`, borderRadius: borderRadius.md,
            backgroundColor: colors.background, border: `1px solid ${colors.borderLight}`,
            color: colors.text.primary, fontSize: fontSize.md, fontWeight: 500, cursor: 'pointer',
          }}>
            {t.auth_sign_out}
          </button>
        </div>
        <button onClick={() => router.back()} style={{
          width: '100%', padding: `${spacing.md}px`, borderRadius: borderRadius.md,
          backgroundColor: colors.primary, border: 'none',
          color: colors.text.inverse, fontSize: fontSize.md, fontWeight: 600, cursor: 'pointer',
        }}>
          {t.auth_go_back}
        </button>
      </div>
    );
  }

  const handleSubmit = async () => {
    setError('');
    setSuccess('');
    if (!email || !password || (mode === 'signup' && !username)) {
      setError(t.auth_fill_all_fields);
      return;
    }
    if (mode === 'signup' && username.length < 3) {
      setError(t.auth_username_too_short);
      return;
    }
    setLoading(true);
    try {
      if (mode === 'signup') {
        await signUp(email, password, username);
        setSuccess(t.auth_signup_success);
      } else {
        await signIn(email, password);
        router.back();
      }
    } catch (err: any) {
      if (err.message === 'USERNAME_TAKEN') setError(t.auth_username_taken);
      else setError(err.message || t.auth_error);
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: '100%', boxSizing: 'border-box' as const,
    padding: `${spacing.md}px ${spacing.md}px ${spacing.md}px 40px`,
    fontSize: fontSize.md, fontFamily: 'inherit', color: colors.text.primary,
    backgroundColor: colors.surface, border: `1px solid ${colors.borderLight}`,
    borderRadius: borderRadius.md, outline: 'none',
  };

  return (
    <div style={{ padding: spacing.lg, paddingBottom: 40, maxWidth: 400, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: spacing.xl }}>
        <div style={{ width: 64, height: 64, borderRadius: borderRadius.full, backgroundColor: colors.primary + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto', marginBottom: spacing.md }}>
          <IoLogIn size={32} color={colors.primary} />
        </div>
        <h2 style={{ fontSize: fontSize.xl, fontWeight: 700, color: colors.text.primary }}>
          {mode === 'signin' ? t.auth_sign_in : t.auth_create_account}
        </h2>
        <p style={{ fontSize: fontSize.sm, color: colors.text.secondary, marginTop: spacing.xs }}>
          {mode === 'signin' ? t.auth_sign_in_desc : t.auth_create_account_desc}
        </p>
      </div>

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: spacing.xs, marginBottom: spacing.lg, backgroundColor: colors.background, borderRadius: borderRadius.md, padding: 3 }}>
        {(['signin', 'signup'] as const).map(m => (
          <button key={m} onClick={() => { setMode(m); setError(''); setSuccess(''); }} style={{
            flex: 1, padding: `${spacing.sm}px`, borderRadius: borderRadius.sm,
            backgroundColor: mode === m ? colors.surface : 'transparent',
            border: mode === m ? `1px solid ${colors.borderLight}` : '1px solid transparent',
            color: mode === m ? colors.text.primary : colors.text.secondary,
            fontSize: fontSize.sm, fontWeight: 600, cursor: 'pointer',
            boxShadow: mode === m ? `0 1px 3px ${colors.shadow}` : 'none',
          }}>
            {m === 'signin' ? t.auth_sign_in : t.auth_sign_up}
          </button>
        ))}
      </div>

      {/* Form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
        {mode === 'signup' && (
          <div style={{ position: 'relative' }}>
            <IoPersonOutline size={18} color={colors.text.tertiary} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
            <input type="text" value={username} onChange={e => setUsername(e.target.value)} placeholder={t.auth_username}
              autoComplete="username" style={inputStyle} />
          </div>
        )}
        <div style={{ position: 'relative' }}>
          <IoMailOutline size={18} color={colors.text.tertiary} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder={t.auth_email}
            autoComplete="email" style={inputStyle} />
        </div>
        <div style={{ position: 'relative' }}>
          <IoLockClosedOutline size={18} color={colors.text.tertiary} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder={t.auth_password}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()} style={inputStyle} />
        </div>
      </div>

      {error && <div style={{ marginTop: spacing.sm, fontSize: fontSize.sm, color: colors.price.up, textAlign: 'center' }}>{error}</div>}
      {success && <div style={{ marginTop: spacing.sm, fontSize: fontSize.sm, color: colors.primary, textAlign: 'center' }}>{success}</div>}

      <button onClick={handleSubmit} disabled={loading} style={{
        width: '100%', padding: `${spacing.md}px`, marginTop: spacing.lg,
        borderRadius: borderRadius.md, backgroundColor: colors.primary, border: 'none',
        color: colors.text.inverse, fontSize: fontSize.md, fontWeight: 600, cursor: loading ? 'wait' : 'pointer',
        opacity: loading ? 0.7 : 1,
      }}>
        {loading ? '...' : mode === 'signin' ? t.auth_sign_in : t.auth_sign_up}
      </button>
    </div>
  );
}
