'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { IoChatbubbleOutline, IoSend, IoPersonCircleOutline } from 'react-icons/io5';
import { colors, spacing, borderRadius, fontSize, formatDateShort } from '@agroamigo/shared';
import { getComments, createComment } from '@agroamigo/shared/api/comments';
import { useAuth } from '@/context/AuthContext';
import { useSettings } from '@/context/SettingsContext';
import { useLanguage } from '@/context/LanguageContext';

interface Props {
  entityType: 'product' | 'market' | 'insumo';
  entityId: string;
}

export function CommentsSection({ entityType, entityId }: Props) {
  const { t } = useLanguage();
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
    } catch (err) {
      console.error(err);
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
    return `${formatDateShort(ts.split('T')[0])} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm }}>
        <IoChatbubbleOutline size={18} color={colors.text.secondary} />
        <span style={{ fontSize: fontSize.md, fontWeight: 700, color: colors.text.primary }}>{t.comments_title}</span>
        {comments.length > 0 && (
          <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>({comments.length})</span>
        )}
      </div>

      {/* Post box */}
      <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.md }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            onFocus={() => { if (!userId) router.push('/auth'); }}
            placeholder={userId ? t.comments_placeholder : t.comments_sign_in_to_comment}
            maxLength={2000}
            rows={2}
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: `${spacing.sm}px ${spacing.md}px`,
              fontSize: fontSize.sm, fontFamily: 'inherit', color: colors.text.primary,
              backgroundColor: colors.background, border: `1px solid ${colors.borderLight}`,
              borderRadius: borderRadius.md, resize: 'vertical', outline: 'none',
              minHeight: 44,
            }}
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={posting || !text.trim()}
          style={{
            alignSelf: 'flex-end',
            width: 40, height: 40, borderRadius: borderRadius.md,
            backgroundColor: text.trim() ? colors.primary : colors.borderLight,
            border: 'none', cursor: text.trim() ? 'pointer' : 'default',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <IoSend size={18} color={text.trim() ? colors.text.inverse : colors.text.tertiary} />
        </button>
      </div>
      {error && <div style={{ fontSize: fontSize.xs, color: colors.price.up, marginBottom: spacing.sm }}>{error}</div>}

      {/* Comments list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: spacing.lg, color: colors.text.tertiary, fontSize: fontSize.sm }}>
          {t.comments_loading}
        </div>
      ) : comments.length === 0 ? (
        <div style={{ textAlign: 'center', padding: spacing.lg, color: colors.text.tertiary, fontSize: fontSize.sm }}>
          {t.comments_empty}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
          {comments.map((c: any) => (
            <div key={c.id} style={{ padding: `${spacing.sm}px`, backgroundColor: colors.background, borderRadius: borderRadius.md }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: spacing.xs, marginBottom: spacing.xs }}>
                <IoPersonCircleOutline size={16} color={colors.text.secondary} />
                <span style={{ fontSize: fontSize.xs, fontWeight: 600, color: colors.text.primary }}>
                  {(c.profiles as any)?.username || t.comments_anonymous}
                </span>
                <span style={{ fontSize: fontSize.xs, color: colors.text.tertiary }}>
                  {formatTimestamp(c.created_at)}
                </span>
              </div>
              <div style={{ fontSize: fontSize.sm, color: colors.text.primary, lineHeight: '18px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {c.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
