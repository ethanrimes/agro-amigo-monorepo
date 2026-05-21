import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class ProductDetailScreen extends StatelessWidget {
  final String productId;
  const ProductDetailScreen({super.key, required this.productId});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text('Producto', style: TextStyle(color: AppColors.textInverse)),
      ),
      child: Center(child: Text('Product detail: $productId')),
    );
  }
}
