import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class MapScreen extends StatelessWidget {
  const MapScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('Mapa (stub)',
          style: TextStyle(color: AppColors.textPrimary, fontSize: AppFontSize.md)),
    );
  }
}
