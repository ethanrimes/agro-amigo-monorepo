import 'package:flutter/cupertino.dart';
import 'colors.dart';

export 'colors.dart';

class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
}

class AppRadius {
  static const double sm = 6;
  static const double md = 10;
  static const double lg = 16;
  static const double xl = 24;
  static const double full = 999;
}

/// Base font sizes — multiply by `SettingsProvider.fontSizeScale` at display time.
class AppFontSize {
  static const double xs = 11;
  static const double sm = 13;
  static const double md = 15;
  static const double lg = 17;
  static const double xl = 20;
  static const double xxl = 24;
  static const double title = 28;
}

CupertinoThemeData buildCupertinoTheme() {
  return const CupertinoThemeData(
    brightness: Brightness.light,
    primaryColor: AppColors.primary,
    primaryContrastingColor: AppColors.textInverse,
    scaffoldBackgroundColor: AppColors.background,
    barBackgroundColor: AppColors.dark,
    textTheme: CupertinoTextThemeData(
      primaryColor: AppColors.textPrimary,
      textStyle: TextStyle(
        fontFamily: '.SF Pro Text',
        fontSize: AppFontSize.md,
        color: AppColors.textPrimary,
      ),
      navTitleTextStyle: TextStyle(
        fontFamily: '.SF Pro Display',
        fontWeight: FontWeight.w700,
        fontSize: AppFontSize.lg,
        color: AppColors.textInverse,
      ),
      navLargeTitleTextStyle: TextStyle(
        fontFamily: '.SF Pro Display',
        fontWeight: FontWeight.w700,
        fontSize: AppFontSize.title,
        color: AppColors.textPrimary,
      ),
      tabLabelTextStyle: TextStyle(
        fontFamily: '.SF Pro Text',
        fontSize: AppFontSize.xs,
        fontWeight: FontWeight.w600,
      ),
    ),
  );
}
