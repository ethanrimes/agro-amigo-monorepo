import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class ProductsScreen extends StatelessWidget {
  final String? categoryId;
  const ProductsScreen({super.key, this.categoryId});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('Productos (stub)',
          style: TextStyle(color: AppColors.textPrimary, fontSize: AppFontSize.md)),
    );
  }
}
