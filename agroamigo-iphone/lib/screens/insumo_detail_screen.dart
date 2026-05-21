import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class InsumoDetailScreen extends StatelessWidget {
  final String insumoId;
  const InsumoDetailScreen({super.key, required this.insumoId});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text('Insumo', style: TextStyle(color: AppColors.textInverse)),
      ),
      child: Center(child: Text('Insumo detail: $insumoId')),
    );
  }
}
