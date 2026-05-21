import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text('Iniciar sesión', style: TextStyle(color: AppColors.textInverse)),
      ),
      child: const SafeArea(child: Center(child: Text('Auth (stub)'))),
    );
  }
}
