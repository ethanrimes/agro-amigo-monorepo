import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';

/// Port of `SearchBar.tsx`.
/// Row with search icon, text field, and a clear button when non-empty.
class AppSearchBar extends StatelessWidget {
  const AppSearchBar({
    super.key,
    required this.value,
    required this.onChanged,
    this.placeholder = 'Buscar...',
    this.controller,
    this.focusNode,
    this.autofocus = false,
  });

  final String value;
  final ValueChanged<String> onChanged;
  final String placeholder;
  final TextEditingController? controller;
  final FocusNode? focusNode;
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md / 2),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          const Icon(CupertinoIcons.search,
              size: 18, color: AppColors.textTertiary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: CupertinoTextField(
              controller: controller,
              focusNode: focusNode,
              autofocus: autofocus,
              placeholder: placeholder,
              placeholderStyle: const TextStyle(
                  color: AppColors.textTertiary, fontSize: AppFontSize.md),
              style: const TextStyle(
                  color: AppColors.textPrimary, fontSize: AppFontSize.md),
              decoration: const BoxDecoration(),
              padding: const EdgeInsets.symmetric(vertical: 2),
              autocorrect: false,
              onChanged: onChanged,
            ),
          ),
          if (value.isNotEmpty) ...[
            const SizedBox(width: AppSpacing.xs),
            GestureDetector(
              onTap: () => onChanged(''),
              child: const Icon(CupertinoIcons.clear_circled,
                  size: 18, color: AppColors.textTertiary),
            ),
          ],
        ],
      ),
    );
  }
}
