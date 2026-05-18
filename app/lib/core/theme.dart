import 'package:flutter/material.dart';

const _emeraldGreen = Color(0xFF059669);
const _emeraldLight = Color(0xFF10B981);
const _amber = Color(0xFFF59E0B);
const _amberDark = Color(0xFFD97706);
const _critical = Color(0xFFEF4444);
const _surface = Color(0xFFF9FAFB);
const _surfaceDark = Color(0xFF111827);

final appTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: _emeraldGreen,
    primary: _emeraldGreen,
    secondary: _amber,
    error: _critical,
    surface: _surface,
    brightness: Brightness.light,
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: _emeraldGreen,
    foregroundColor: Colors.white,
    elevation: 0,
    centerTitle: false,
    titleTextStyle: TextStyle(
      color: Colors.white,
      fontSize: 20,
      fontWeight: FontWeight.w700,
      letterSpacing: -0.3,
    ),
  ),
  cardTheme: CardThemeData(
    elevation: 0,
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    color: Colors.white,
    surfaceTintColor: Colors.transparent,
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      backgroundColor: _emeraldGreen,
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 24),
      textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: Colors.white,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: Color(0xFFE5E7EB)),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: Color(0xFFE5E7EB)),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: _emeraldGreen, width: 2),
    ),
  ),
  bottomNavigationBarTheme: const BottomNavigationBarThemeData(
    selectedItemColor: _emeraldGreen,
    unselectedItemColor: Color(0xFF9CA3AF),
    backgroundColor: Colors.white,
    type: BottomNavigationBarType.fixed,
    elevation: 8,
  ),
  chipTheme: ChipThemeData(
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  ),
  fontFamily: 'Inter',
);

final appDarkTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: _emeraldLight,
    primary: _emeraldLight,
    secondary: _amber,
    error: _critical,
    surface: _surfaceDark,
    brightness: Brightness.dark,
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: Color(0xFF1F2937),
    foregroundColor: Colors.white,
    elevation: 0,
    centerTitle: false,
  ),
  fontFamily: 'Inter',
);

// Colores de urgencia para uso en widgets
class UrgencyColors {
  static const critical = _critical;
  static const high = _amber;
  static const medium = Color(0xFF3B82F6);
  static const low = _emeraldGreen;

  static Color forLevel(String level) {
    switch (level.toUpperCase()) {
      case 'CRÍTICO':
      case 'CRITICO':
        return critical;
      case 'ALTO':
        return high;
      case 'MEDIO':
        return medium;
      default:
        return low;
    }
  }

  static Color forDays(int days) {
    if (days <= 1) return critical;
    if (days <= 3) return high;
    if (days <= 5) return medium;
    return low;
  }
}
