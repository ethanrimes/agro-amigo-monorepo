import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import 'state/settings_provider.dart';
import 'theme/theme.dart';
import 'screens/home_screen.dart';
import 'screens/products_screen.dart';
import 'screens/markets_screen.dart';
import 'screens/insumos_screen.dart';
import 'screens/map_screen.dart';
import 'screens/settings_screen.dart';

/// Root tab scaffold — equivalent to `app/(tabs)/_layout.tsx`.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  @override
  Widget build(BuildContext context) {
    final t = context.watch<SettingsProvider>().t;

    return CupertinoTabScaffold(
      tabBar: CupertinoTabBar(
        backgroundColor: AppColors.dark,
        activeColor: AppColors.primaryLight,
        inactiveColor: AppColors.textTertiary,
        height: 60,
        border: const Border(
          top: BorderSide(color: AppColors.darkSurface, width: 0.5),
        ),
        items: [
          BottomNavigationBarItem(
            icon: _tabIcon(CupertinoIcons.home),
            label: t.nav_home_tab,
          ),
          BottomNavigationBarItem(
            icon: _tabIcon(CupertinoIcons.leaf_arrow_circlepath),
            label: t.nav_products,
          ),
          BottomNavigationBarItem(
            icon: _tabIcon(CupertinoIcons.cart),
            label: t.nav_markets,
          ),
          BottomNavigationBarItem(
            icon: _tabIcon(CupertinoIcons.lab_flask),
            label: t.nav_inputs,
          ),
          BottomNavigationBarItem(
            icon: _tabIcon(CupertinoIcons.map),
            label: t.nav_map,
          ),
        ],
      ),
      tabBuilder: (context, index) {
        return CupertinoTabView(
          builder: (context) {
            switch (index) {
              case 0:
                return _withNav(context, title: 'AgroAmigo', child: const HomeScreen());
              case 1:
                return _withNav(context, title: t.nav_products, child: const ProductsScreen());
              case 2:
                return _withNav(context, title: t.nav_markets, child: const MarketsScreen());
              case 3:
                return _withNav(context, title: t.nav_inputs, child: const InsumosScreen());
              case 4:
                return _withNav(context, title: t.nav_map, child: const MapScreen());
              default:
                return const SizedBox.shrink();
            }
          },
        );
      },
    );
  }

  Widget _tabIcon(IconData icon) {
    return Transform.translate(
      offset: const Offset(0, 6),
      child: Icon(icon),
    );
  }

  Widget _withNav(BuildContext context, {required String title, required Widget child}) {
    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text(title,
            style: const TextStyle(color: AppColors.textInverse, fontWeight: FontWeight.w700)),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.settings, color: AppColors.textInverse, size: 22),
          onPressed: () {
            Navigator.of(context).push(
              CupertinoPageRoute(builder: (_) => const SettingsScreen()),
            );
          },
        ),
      ),
      child: SafeArea(bottom: false, child: child),
    );
  }
}
