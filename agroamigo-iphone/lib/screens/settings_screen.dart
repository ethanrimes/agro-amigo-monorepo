import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text('Configuración', style: TextStyle(color: AppColors.textInverse)),
      ),
      child: const SafeArea(
        child: Center(child: Text('Settings (stub)')),
      ),
    );
  }
}
