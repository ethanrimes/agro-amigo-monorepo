import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import 'package:agroamigo_iphone/theme/theme.dart';
import 'package:agroamigo_iphone/state/settings_provider.dart';
import 'package:agroamigo_iphone/state/auth_provider.dart';
import 'package:agroamigo_iphone/api/comments_api.dart';

/// Port of `CommentsSection.tsx`.
/// Shows comment list + post box for a given entity.
/// Respects `settings.commentsEnabled`; redirects to auth if not signed in.
class CommentsSection extends StatefulWidget {
  const CommentsSection({
    super.key,
    required this.entityType,
    required this.entityId,
  });

  final String entityType; // 'product' | 'market' | 'insumo'
  final String entityId;

  @override
  State<CommentsSection> createState() => _CommentsSectionState();
}

class _CommentsSectionState extends State<CommentsSection> {
  List<dynamic> _comments = [];
  bool _loading = true;
  String _text = '';
  bool _posting = false;
  String _error = '';
  final _controller = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(CommentsSection old) {
    super.didUpdateWidget(old);
    if (old.entityType != widget.entityType ||
        old.entityId != widget.entityId) {
      _load();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final data =
          await getComments(widget.entityType, widget.entityId, limit: 50);
      setState(() => _comments = data ?? []);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _handleSubmit() async {
    final auth = context.read<AuthProvider>();
    if (auth.userId == null || auth.profile == null) {
      Navigator.of(context).pushNamed('/auth');
      return;
    }
    final trimmed = _text.trim();
    if (trimmed.isEmpty || _posting) return;
    setState(() {
      _posting = true;
      _error = '';
    });
    try {
      final newComment = await createComment(
        auth.userId!,
        widget.entityType,
        widget.entityId,
        trimmed,
      );
      setState(() {
        _comments = [newComment, ..._comments];
        _text = '';
        _controller.clear();
      });
    } catch (err) {
      final t = context.read<SettingsProvider>().t;
      setState(() => _error = err.toString().isNotEmpty
          ? err.toString()
          : t.comments_error);
    } finally {
      if (mounted) setState(() => _posting = false);
    }
  }

  String _formatTimestamp(String ts) {
    final d = DateTime.tryParse(ts)?.toLocal();
    if (d == null) return ts;
    const months = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
    ];
    final h = d.hour.toString().padLeft(2, '0');
    final m = d.minute.toString().padLeft(2, '0');
    return '${d.day} ${months[d.month - 1]} $h:$m';
  }

  @override
  Widget build(BuildContext context) {
    final sp = context.watch<SettingsProvider>();
    if (!sp.settings.commentsEnabled) return const SizedBox.shrink();
    final t = sp.t;
    final auth = context.watch<AuthProvider>();
    final userId = auth.userId;

    final canSend = _text.trim().isNotEmpty && !_posting;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header
        Row(
          children: [
            const Icon(CupertinoIcons.chat_bubble,
                size: 18, color: AppColors.textSecondary),
            const SizedBox(width: AppSpacing.sm),
            Text(t.comments_title,
                style: const TextStyle(
                    fontSize: AppFontSize.md,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary)),
            if (_comments.isNotEmpty) ...[
              const SizedBox(width: AppSpacing.xs),
              Text('(${_comments.length})',
                  style: const TextStyle(
                      fontSize: AppFontSize.xs,
                      color: AppColors.textTertiary)),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.sm),

        // Post row
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                constraints: const BoxConstraints(minHeight: 44),
                decoration: BoxDecoration(
                  color: AppColors.background,
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  border: Border.all(color: AppColors.borderLight),
                ),
                child: CupertinoTextField(
                  controller: _controller,
                  placeholder: userId != null
                      ? t.comments_placeholder
                      : t.comments_sign_in_to_comment,
                  placeholderStyle: const TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: AppFontSize.sm),
                  style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: AppFontSize.sm),
                  maxLength: 2000,
                  maxLines: null,
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                  decoration: const BoxDecoration(),
                  onChanged: (v) => setState(() => _text = v),
                  onTap: () {
                    if (userId == null) {
                      Navigator.of(context).pushNamed('/auth');
                    }
                  },
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: canSend ? _handleSubmit : null,
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: canSend ? AppColors.primary : AppColors.borderLight,
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
                child: _posting
                    ? const CupertinoActivityIndicator()
                    : Icon(
                        CupertinoIcons.paperplane_fill,
                        size: 18,
                        color: canSend
                            ? AppColors.textInverse
                            : AppColors.textTertiary,
                      ),
              ),
            ),
          ],
        ),

        if (_error.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(_error,
              style: const TextStyle(
                  fontSize: AppFontSize.xs, color: AppColors.priceUp)),
        ],

        const SizedBox(height: AppSpacing.sm),

        // Comments list
        if (_loading)
          const Padding(
            padding: EdgeInsets.all(AppSpacing.lg),
            child: CupertinoActivityIndicator(),
          )
        else if (_comments.isEmpty)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Center(
              child: Text(t.comments_empty,
                  style: const TextStyle(
                      fontSize: AppFontSize.sm,
                      color: AppColors.textTertiary)),
            ),
          )
        else
          Column(
            children: [
              for (final c in _comments)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Container(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    decoration: BoxDecoration(
                      color: AppColors.background,
                      borderRadius: BorderRadius.circular(AppRadius.md),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Icon(CupertinoIcons.person_circle,
                                size: 16, color: AppColors.textSecondary),
                            const SizedBox(width: AppSpacing.xs),
                            Text(
                              (c['profiles'] as Map?)?['username'] as String? ??
                                  t.comments_anonymous,
                              style: const TextStyle(
                                  fontSize: AppFontSize.xs,
                                  fontWeight: FontWeight.w600,
                                  color: AppColors.textPrimary),
                            ),
                            const SizedBox(width: AppSpacing.xs),
                            Text(
                              _formatTimestamp(
                                  c['created_at'] as String? ?? ''),
                              style: const TextStyle(
                                  fontSize: AppFontSize.xs,
                                  color: AppColors.textTertiary),
                            ),
                          ],
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          c['content'] as String? ?? '',
                          style: const TextStyle(
                              fontSize: AppFontSize.sm,
                              color: AppColors.textPrimary,
                              height: 1.4),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}
