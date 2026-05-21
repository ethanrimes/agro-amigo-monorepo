import 'package:flutter/cupertino.dart';
import '../theme/theme.dart';

class MarketDetailScreen extends StatelessWidget {
  final String marketId;
  const MarketDetailScreen({super.key, required this.marketId});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text('Mercado', style: TextStyle(color: AppColors.textInverse)),
      ),
      child: Center(child: Text('Market detail: $marketId')),
    );
  }
}
