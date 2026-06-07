import 'package:flutter/material.dart';

const _emeraldGreen = Color(0xFF059669);
const _emeraldLight = Color(0xFF10B981);
const _amber = Color(0xFFF59E0B);
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

// ── Shimmer loading — reemplaza CircularProgressIndicator ─────────────────────
// Uso: ShimmerBox(width: double.infinity, height: 80)
// Uso en lista: ShimmerList(count: 3, itemHeight: 88)

class ShimmerBox extends StatefulWidget {
  final double width;
  final double height;
  final double borderRadius;

  const ShimmerBox({
    super.key,
    required this.width,
    required this.height,
    this.borderRadius = 12,
  });

  @override
  State<ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<ShimmerBox>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) {
        final t = _ctrl.value;
        return Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(widget.borderRadius),
            gradient: LinearGradient(
              begin: Alignment.centerLeft,
              end: Alignment.centerRight,
              stops: [
                (t - 0.35).clamp(0.0, 1.0),
                t.clamp(0.0, 1.0),
                (t + 0.35).clamp(0.0, 1.0),
              ],
              colors: const [
                Color(0xFFE5E7EB),
                Color(0xFFF3F4F6),
                Color(0xFFE5E7EB),
              ],
            ),
          ),
        );
      },
    );
  }
}

class ShimmerList extends StatelessWidget {
  final int count;
  final double itemHeight;
  final EdgeInsets padding;

  const ShimmerList({
    super.key,
    this.count = 4,
    this.itemHeight = 88,
    this.padding = const EdgeInsets.all(16),
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header shimmer
          const ShimmerBox(width: 180, height: 14),
          const SizedBox(height: 12),
          ...List.generate(count, (i) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: ShimmerBox(
              width: double.infinity,
              height: itemHeight,
            ),
          )),
        ],
      ),
    );
  }
}

// Shimmer para las KPI cards del dashboard (2 columnas)
class ShimmerKpiGrid extends StatelessWidget {
  const ShimmerKpiGrid({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
      child: Column(
        children: [
          Row(children: const [
            Expanded(child: ShimmerBox(width: double.infinity, height: 80)),
            SizedBox(width: 12),
            Expanded(child: ShimmerBox(width: double.infinity, height: 80)),
          ]),
          const SizedBox(height: 12),
          Row(children: const [
            Expanded(child: ShimmerBox(width: double.infinity, height: 80)),
            SizedBox(width: 12),
            Expanded(child: ShimmerBox(width: double.infinity, height: 80)),
          ]),
          const SizedBox(height: 20),
          const ShimmerBox(width: double.infinity, height: 120),
          const SizedBox(height: 16),
          const ShimmerBox(width: double.infinity, height: 90),
        ],
      ),
    );
  }
}
