import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/actions/actions_provider.dart';
import 'l10n.dart';
import 'theme.dart';

class ShellScaffold extends ConsumerWidget {
  final Widget child;
  const ShellScaffold({super.key, required this.child});

  int _locationToIndex(String location) {
    if (location.startsWith('/scan')) return 1;
    if (location.startsWith('/actions')) return 2;
    if (location.startsWith('/map')) return 3;
    if (location.startsWith('/reports')) return 4;
    return 0;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final currentIndex = _locationToIndex(location);

    // Badge count for critical actions
    final actionsAsync = ref.watch(pendingActionsProvider);
    final criticalCount = actionsAsync.when(
      data: (actions) => actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length,
      loading: () => 0,
      error: (_, __) => 0,
    );

    Widget actionIcon(bool active) {
      final icon = Icon(active ? Icons.task_alt : Icons.task_alt_outlined);
      if (criticalCount == 0) return icon;
      return Badge(
        label: Text(criticalCount > 9 ? '9+' : '$criticalCount'),
        backgroundColor: UrgencyColors.critical,
        textColor: Colors.white,
        child: icon,
      );
    }

    return Scaffold(
      body: child,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: currentIndex,
        onTap: (index) {
          switch (index) {
            case 0:
              context.go('/');
            case 1:
              context.go('/scan');
            case 2:
              context.go('/actions');
            case 3:
              context.go('/map');
            case 4:
              context.go('/reports');
          }
        },
        items: [
          BottomNavigationBarItem(
            icon: const Icon(Icons.dashboard_outlined),
            activeIcon: const Icon(Icons.dashboard),
            label: tr(ref, 'nav_dashboard'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.qr_code_scanner_outlined),
            activeIcon: const Icon(Icons.qr_code_scanner),
            label: tr(ref, 'nav_scan'),
          ),
          BottomNavigationBarItem(
            icon: actionIcon(false),
            activeIcon: actionIcon(true),
            label: tr(ref, 'nav_actions'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.map_outlined),
            activeIcon: const Icon(Icons.map),
            label: tr(ref, 'nav_map'),
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.bar_chart_outlined),
            activeIcon: const Icon(Icons.bar_chart),
            label: tr(ref, 'nav_reports'),
          ),
        ],
      ),
    );
  }
}
