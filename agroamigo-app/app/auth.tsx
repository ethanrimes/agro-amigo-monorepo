import React, { useState } from 'react';
import { View, Text, TextInput, Pressable, ScrollView, StyleSheet } from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../src/theme';
import { signUp, signIn } from '../src/api/auth';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/lib/useTranslation';

export default function AuthScreen() {
  const router = useRouter();
  const { userId, profile, signOut } = useAuth();
  const t = useTranslation();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');

  if (userId && profile) {
    return (
      <>
        <Stack.Screen options={{ title: t.auth_account }} />
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
          <View style={styles.profileCard}>
            <View style={styles.avatar}>
              <Ionicons name="person-outline" size={24} color={colors.primary} />
            </View>
            <Text style={styles.profileName}>{profile.username}</Text>
            <Text style={styles.profileMeta}>{t.auth_member_since} {new Date(profile.created_at).toLocaleDateString()}</Text>
            <Pressable onPress={async () => { await signOut(); }} style={styles.signOutBtn}>
              <Text style={styles.signOutText}>{t.auth_sign_out}</Text>
            </Pressable>
          </View>
          <Pressable onPress={() => router.back()} style={styles.primaryBtn}>
            <Text style={styles.primaryBtnText}>{t.auth_go_back}</Text>
          </Pressable>
        </ScrollView>
      </>
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

  return (
    <>
      <Stack.Screen options={{ title: mode === 'signin' ? t.auth_sign_in : t.auth_create_account }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <View style={styles.iconWrap}>
          <Ionicons name="log-in-outline" size={32} color={colors.primary} />
        </View>
        <Text style={styles.heading}>{mode === 'signin' ? t.auth_sign_in : t.auth_create_account}</Text>
        <Text style={styles.subheading}>{mode === 'signin' ? t.auth_sign_in_desc : t.auth_create_account_desc}</Text>

        {/* Mode toggle */}
        <View style={styles.modeToggle}>
          {(['signin', 'signup'] as const).map(m => (
            <Pressable key={m} onPress={() => { setMode(m); setError(''); setSuccess(''); }}
              style={[styles.modeBtn, mode === m && styles.modeBtnActive]}>
              <Text style={[styles.modeBtnText, mode === m && styles.modeBtnTextActive]}>
                {m === 'signin' ? t.auth_sign_in : t.auth_sign_up}
              </Text>
            </Pressable>
          ))}
        </View>

        {/* Form */}
        {mode === 'signup' && (
          <View style={styles.inputWrap}>
            <Ionicons name="person-outline" size={18} color={colors.text.tertiary} style={styles.inputIcon} />
            <TextInput value={username} onChangeText={setUsername} placeholder={t.auth_username}
              placeholderTextColor={colors.text.tertiary} autoCapitalize="none" style={styles.input} />
          </View>
        )}
        <View style={styles.inputWrap}>
          <Ionicons name="mail-outline" size={18} color={colors.text.tertiary} style={styles.inputIcon} />
          <TextInput value={email} onChangeText={setEmail} placeholder={t.auth_email}
            placeholderTextColor={colors.text.tertiary} keyboardType="email-address" autoCapitalize="none" style={styles.input} />
        </View>
        <View style={styles.inputWrap}>
          <Ionicons name="lock-closed-outline" size={18} color={colors.text.tertiary} style={styles.inputIcon} />
          <TextInput value={password} onChangeText={setPassword} placeholder={t.auth_password}
            placeholderTextColor={colors.text.tertiary} secureTextEntry onSubmitEditing={handleSubmit} style={styles.input} />
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        {success ? <Text style={styles.successText}>{success}</Text> : null}

        <Pressable onPress={handleSubmit} disabled={loading} style={[styles.primaryBtn, loading && { opacity: 0.7 }]}>
          <Text style={styles.primaryBtnText}>{loading ? '...' : mode === 'signin' ? t.auth_sign_in : t.auth_sign_up}</Text>
        </Pressable>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: 40, maxWidth: 400, alignSelf: 'center', width: '100%' },
  iconWrap: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primary + '15', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: spacing.md },
  heading: { fontSize: fontSize.xl, fontWeight: '700', color: colors.text.primary, textAlign: 'center' },
  subheading: { fontSize: fontSize.sm, color: colors.text.secondary, textAlign: 'center', marginTop: spacing.xs, marginBottom: spacing.lg },
  modeToggle: { flexDirection: 'row', gap: spacing.xs, backgroundColor: colors.background, borderRadius: borderRadius.md, padding: 3, marginBottom: spacing.lg },
  modeBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: borderRadius.sm, alignItems: 'center', borderWidth: 1, borderColor: 'transparent' },
  modeBtnActive: { backgroundColor: colors.surface, borderColor: colors.borderLight },
  modeBtnText: { fontSize: fontSize.sm, fontWeight: '600', color: colors.text.secondary },
  modeBtnTextActive: { color: colors.text.primary },
  inputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.borderLight, borderRadius: borderRadius.md, marginBottom: spacing.md },
  inputIcon: { marginLeft: 12 },
  input: { flex: 1, paddingVertical: spacing.md, paddingHorizontal: spacing.md, fontSize: fontSize.md, color: colors.text.primary },
  errorText: { fontSize: fontSize.sm, color: colors.price.up, textAlign: 'center', marginBottom: spacing.sm },
  successText: { fontSize: fontSize.sm, color: colors.primary, textAlign: 'center', marginBottom: spacing.sm },
  primaryBtn: { backgroundColor: colors.primary, paddingVertical: spacing.md, borderRadius: borderRadius.md, alignItems: 'center', marginTop: spacing.md },
  primaryBtnText: { color: colors.text.inverse, fontSize: fontSize.md, fontWeight: '600' },
  profileCard: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.borderLight, alignItems: 'center', marginBottom: spacing.lg },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.primary + '15', alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm },
  profileName: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text.primary },
  profileMeta: { fontSize: fontSize.xs, color: colors.text.tertiary, marginBottom: spacing.md },
  signOutBtn: { backgroundColor: colors.background, borderWidth: 1, borderColor: colors.borderLight, borderRadius: borderRadius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, width: '100%', alignItems: 'center' },
  signOutText: { fontSize: fontSize.sm, color: colors.text.primary },
});
