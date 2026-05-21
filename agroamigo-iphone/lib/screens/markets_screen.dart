import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class MarketsScreen extends StatelessWidget {
  const MarketsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('Mercados (stub)',
          style: TextStyle(color: AppColors.textPrimary, fontSize: AppFontSize.md)),
    );
  }
}
