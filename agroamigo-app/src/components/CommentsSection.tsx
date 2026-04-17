import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TextInput, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../theme';
import { getComments, createComment } from '../api/comments';
import { useAuth } from '../context/AuthContext';
import { useSettings } from '../context/SettingsContext';
import { useTranslation } from '../lib/useTranslation';

interface Props {
  entityType: 'product' | 'market' | 'insumo';
  entityId: string;
}

export function CommentsSection({ entityType, entityId }: Props) {
  const t = useTranslation();
  const { userId, profile } = useAuth();
  const { settings } = useSettings();
  const router = useRouter();
  const [comments, setComments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await getComments(entityType, entityId, 50);
      setComments(data || []);
    } catch {
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => { load(); }, [load]);

  if (!settings.commentsEnabled) return null;

  const handleSubmit = async () => {
    if (!userId || !profile) {
      router.push('/auth');
      return;
    }
    const trimmed = text.trim();
    if (!trimmed || posting) return;
    setPosting(true);
    setError('');
    try {
      const newComment = await createComment(userId, entityType, entityId, trimmed);
      setComments(prev => [newComment, ...prev]);
      setText('');
    } catch (err: any) {
      setError(err.message || t.comments_error);
    } finally {
      setPosting(false);
    }
  };

  const formatTimestamp = (ts: string) => {
    const d = new Date(ts);
    const months = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
  };

  return (
    <View>
      <View style={styles.header}>
        <Ionicons name="chatbubble-outline" size={18} color={colors.text.secondary} />
        <Text style={styles.title}>{t.comments_title}</Text>
        {comments.length > 0 && <Text style={styles.count}>({comments.length})</Text>}
      </View>

      {/* Post box */}
      <View style={styles.postRow}>
        <TextInput
          value={text}
          onChangeText={setText}
          onFocus={() => { if (!userId) router.push('/auth'); }}
          placeholder={userId ? t.comments_placeholder : t.comments_sign_in_to_comment}
          placeholderTextColor={colors.text.tertiary}
          maxLength={2000}
          multiline
          style={styles.textInput}
        />
        <Pressable onPress={handleSubmit} disabled={posting || !text.trim()} style={[styles.sendBtn, text.trim() ? styles.sendBtnActive : null]}>
          {posting ? <ActivityIndicator size="small" color={colors.text.inverse} /> : <Ionicons name="send" size={18} color={text.trim() ? colors.text.inverse : colors.text.tertiary} />}
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {/* Comments list */}
      {loading ? (
        <ActivityIndicator size="small" color={colors.text.tertiary} style={{ padding: spacing.lg }} />
      ) : comments.length === 0 ? (
        <Text style={styles.empty}>{t.comments_empty}</Text>
      ) : (
        <View style={{ gap: spacing.sm }}>
          {comments.map((c: any) => (
            <View key={c.id} style={styles.comment}>
              <View style={styles.commentHeader}>
                <Ionicons name="person-circle-outline" size={16} color={colors.text.secondary} />
                <Text style={styles.username}>{(c.profiles as any)?.username || t.comments_anonymous}</Text>
                <Text style={styles.timestamp}>{formatTimestamp(c.created_at)}</Text>
              </View>
              <Text style={styles.content}>{c.content}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
  title: { fontSize: fontSize.md, fontWeight: '700', color: colors.text.primary },
  count: { fontSize: fontSize.xs, color: colors.text.tertiary },
  postRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  textInput: {
    flex: 1, minHeight: 44, padding: spacing.sm, paddingHorizontal: spacing.md,
    fontSize: fontSize.sm, color: colors.text.primary,
    backgroundColor: colors.background, borderWidth: 1, borderColor: colors.borderLight,
    borderRadius: borderRadius.md, textAlignVertical: 'top',
  },
  sendBtn: {
    alignSelf: 'flex-end', width: 40, height: 40, borderRadius: borderRadius.md,
    backgroundColor: colors.borderLight, alignItems: 'center', justifyContent: 'center',
  },
  sendBtnActive: { backgroundColor: colors.primary },
  error: { fontSize: fontSize.xs, color: colors.price.up, marginBottom: spacing.sm },
  empty: { textAlign: 'center', padding: spacing.lg, fontSize: fontSize.sm, color: colors.text.tertiary },
  comment: { padding: spacing.sm, backgroundColor: colors.background, borderRadius: borderRadius.md },
  commentHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, marginBottom: spacing.xs },
  username: { fontSize: fontSize.xs, fontWeight: '600', color: colors.text.primary },
  timestamp: { fontSize: fontSize.xs, color: colors.text.tertiary },
  content: { fontSize: fontSize.sm, color: colors.text.primary, lineHeight: 18 },
});
