import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/auth_api.dart';
import '../state/auth_provider.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../translations/translations.dart';

enum _AuthMode { signIn, signUp }

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  _AuthMode _mode = _AuthMode.signIn;
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _username = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _username.dispose();
    super.dispose();
  }

  Future<void> _showAlert(String title, String message) async {
    if (!mounted) return;
    await showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Future<void> _submit(Translations t) async {
    final email = _email.text.trim();
    final password = _password.text;
    final username = _username.text.trim();

    if (email.isEmpty ||
        password.isEmpty ||
        (_mode == _AuthMode.signUp && username.isEmpty)) {
      await _showAlert(t.auth_error, t.auth_fill_all_fields);
      return;
    }
    if (_mode == _AuthMode.signUp && username.length < 3) {
      await _showAlert(t.auth_error, t.auth_username_too_short);
      return;
    }

    setState(() => _loading = true);
    try {
      if (_mode == _AuthMode.signUp) {
        await AuthApi.signUp(email, password, username);
        await _showAlert(t.auth_sign_up, t.auth_signup_success);
        if (mounted) {
          setState(() {
            _mode = _AuthMode.signIn;
            _password.clear();
          });
        }
      } else {
        await AuthApi.signIn(email, password);
        if (mounted) {
          await context.read<AuthProvider>().refreshProfile();
          if (mounted) Navigator.of(context).pop();
        }
      }
    } catch (err) {
      final msg = err.toString();
      if (msg.contains('USERNAME_TAKEN')) {
        await _showAlert(t.auth_error, t.auth_username_taken);
      } else {
        await _showAlert(t.auth_error, msg.isNotEmpty ? msg : t.auth_error);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final auth = context.watch<AuthProvider>();
    final t = settings.t;
    final scale = settings.settings.fontSizeScale;

    final title = auth.userId != null && auth.profile != null
        ? t.auth_account
        : (_mode == _AuthMode.signIn ? t.auth_sign_in : t.auth_create_account);

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text(title,
            style: const TextStyle(color: AppColors.textInverse, fontWeight: FontWeight.w700)),
        previousPageTitle: t.nav_settings,
      ),
      child: SafeArea(
        child: auth.userId != null && auth.profile != null
            ? _signedInBody(context, t, scale, auth)
            : _formBody(context, t, scale),
      ),
    );
  }

  Widget _signedInBody(
      BuildContext context, Translations t, double scale, AuthProvider auth) {
    final profile = auth.profile!;
    String memberSince = profile.createdAt;
    try {
      final dt = DateTime.parse(profile.createdAt).toLocal();
      memberSince =
          '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
    } catch (_) {}

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Container(
          padding: const EdgeInsets.all(AppSpacing.lg),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.md),
            border: Border.all(color: AppColors.borderLight),
          ),
          child: Column(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
                  color: Color(0x262D7D46),
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: const Icon(CupertinoIcons.person,
                    size: 28, color: AppColors.primary),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(profile.username,
                  style: TextStyle(
                    fontSize: AppFontSize.lg * scale,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  )),
              const SizedBox(height: AppSpacing.xs),
              Text('${t.auth_member_since} $memberSince',
                  style: TextStyle(
                    fontSize: AppFontSize.xs * scale,
                    color: AppColors.textTertiary,
                  )),
              const SizedBox(height: AppSpacing.lg),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton(
                  color: AppColors.background,
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  onPressed: () async {
                    await context.read<AuthProvider>().signOut();
                    if (mounted) setState(() {});
                  },
                  child: Text(t.auth_sign_out,
                      style: TextStyle(
                        fontSize: AppFontSize.sm * scale,
                        color: AppColors.textPrimary,
                      )),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        SizedBox(
          width: double.infinity,
          child: CupertinoButton.filled(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(t.auth_go_back),
          ),
        ),
      ],
    );
  }

  Widget _formBody(BuildContext context, Translations t, double scale) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Center(
          child: Container(
            width: 64,
            height: 64,
            decoration: const BoxDecoration(
              color: Color(0x262D7D46),
              shape: BoxShape.circle,
            ),
            alignment: Alignment.center,
            child: const Icon(CupertinoIcons.square_arrow_right,
                size: 28, color: AppColors.primary),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Text(
          _mode == _AuthMode.signIn ? t.auth_sign_in : t.auth_create_account,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppFontSize.xl * scale,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          _mode == _AuthMode.signIn
              ? t.auth_sign_in_desc
              : t.auth_create_account_desc,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppFontSize.sm * scale,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        CupertinoSlidingSegmentedControl<_AuthMode>(
          groupValue: _mode,
          onValueChanged: (v) {
            if (v != null) setState(() => _mode = v);
          },
          children: {
            _AuthMode.signIn: Padding(
              padding: const EdgeInsets.symmetric(
                  vertical: AppSpacing.xs, horizontal: AppSpacing.md),
              child: Text(t.auth_sign_in,
                  style: TextStyle(fontSize: AppFontSize.sm * scale)),
            ),
            _AuthMode.signUp: Padding(
              padding: const EdgeInsets.symmetric(
                  vertical: AppSpacing.xs, horizontal: AppSpacing.md),
              child: Text(t.auth_sign_up,
                  style: TextStyle(fontSize: AppFontSize.sm * scale)),
            ),
          },
        ),
        const SizedBox(height: AppSpacing.lg),
        if (_mode == _AuthMode.signUp) ...[
          _input(
            controller: _username,
            placeholder: t.auth_username,
            icon: CupertinoIcons.person,
            scale: scale,
            keyboardType: TextInputType.text,
          ),
          const SizedBox(height: AppSpacing.md),
        ],
        _input(
          controller: _email,
          placeholder: t.auth_email,
          icon: CupertinoIcons.mail,
          scale: scale,
          keyboardType: TextInputType.emailAddress,
        ),
        const SizedBox(height: AppSpacing.md),
        _input(
          controller: _password,
          placeholder: t.auth_password,
          icon: CupertinoIcons.lock,
          scale: scale,
          obscure: true,
          onSubmitted: (_) => _submit(t),
        ),
        const SizedBox(height: AppSpacing.lg),
        SizedBox(
          width: double.infinity,
          child: CupertinoButton.filled(
            onPressed: _loading ? null : () => _submit(t),
            child: _loading
                ? const CupertinoActivityIndicator(color: AppColors.textInverse)
                : Text(_mode == _AuthMode.signIn
                    ? t.auth_sign_in
                    : t.auth_sign_up),
          ),
        ),
      ],
    );
  }

  Widget _input({
    required TextEditingController controller,
    required String placeholder,
    required IconData icon,
    required double scale,
    bool obscure = false,
    TextInputType? keyboardType,
    ValueChanged<String>? onSubmitted,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.borderLight),
      ),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.textTertiary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: CupertinoTextField(
              controller: controller,
              placeholder: placeholder,
              decoration: const BoxDecoration(),
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
              obscureText: obscure,
              keyboardType: keyboardType,
              autocorrect: false,
              enableSuggestions: !obscure,
              textInputAction: onSubmitted != null
                  ? TextInputAction.go
                  : TextInputAction.next,
              onSubmitted: onSubmitted,
              style: TextStyle(
                fontSize: AppFontSize.md * scale,
                color: AppColors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
