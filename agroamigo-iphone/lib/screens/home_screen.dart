import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

/// Stub — replaced by the home_screen agent with a full port of
/// `agroamigo-app/app/(tabs)/index.tsx`.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.lg),
        child: Text(
          'AgroAmigo — Home (stub, awaiting full port)',
          style: TextStyle(color: AppColors.textPrimary, fontSize: AppFontSize.md),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
