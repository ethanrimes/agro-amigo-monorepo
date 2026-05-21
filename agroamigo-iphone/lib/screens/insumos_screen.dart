import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class InsumosScreen extends StatelessWidget {
  const InsumosScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('Insumos (stub)',
          style: TextStyle(color: AppColors.textPrimary, fontSize: AppFontSize.md)),
    );
  }
}
