import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/actions/actions_provider.dart';
import 'l10n.dart';
import 'theme.dart';
import 'user_role_provider.dart';

// Definición de un tab con su ruta, iconos y rol mínimo requerido
class _NavTab {
  final String route;
  final IconData icon;
  final IconData activeIcon;
  final String labelKey;
  final UserRole minRole;

  const _NavTab({
    required this.route,
    required this.icon,
    required this.activeIcon,
    required this.labelKey,
    this.minRole = UserRole.staff,
  });
}

const _allTabs = [
  _NavTab(route: '/',        icon: Icons.dashboard_outlined,        activeIcon: Icons.dashboard,             labelKey: 'nav_dashboard'),
  _NavTab(route: '/scan',    icon: Icons.qr_code_scanner_outlined,  activeIcon: Icons.qr_code_scanner,       labelKey: 'nav_scan'),
  _NavTab(route: '/actions', icon: Icons.task_alt_outlined,         activeIcon: Icons.task_alt,               labelKey: 'nav_actions'),
  _NavTab(route: '/map',     icon: Icons.map_outlined,              activeIcon: Icons.map,                    labelKey: 'nav_map'),
  _NavTab(route: '/reports', icon: Icons.bar_chart_outlined,        activeIcon: Icons.bar_chart,              labelKey: 'nav_reports',  minRole: UserRole.manager),
  _NavTab(route: '/agents',  icon: Icons.psychology_outlined,       activeIcon: Icons.psychology,             labelKey: 'nav_agents',   minRole: UserRole.manager),
  _NavTab(route: '/chat',    icon: Icons.chat_bubble_outline_rounded, activeIcon: Icons.chat_bubble_rounded,  labelKey: 'nav_chat'),
];

class ShellScaffold extends ConsumerWidget {
  final Widget child;
  const ShellScaffold({super.key, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    // Role-based tab filtering: staff ve solo sus tabs, manager ve todos
    final roleAsync = ref.watch(userRoleProvider);
    final userRole = roleAsync.when(
      data: (r) => r,
      loading: () => UserRole.staff,
      error: (_, __) => UserRole.staff,
    );

    // Tabs visibles para este rol
    final visibleTabs = _allTabs.where((t) => userRole.index >= t.minRole.index).toList();

    // Índice del tab actual dentro de los visibles
    final currentIndex = () {
      for (int i = 0; i < visibleTabs.length; i++) {
        final r = visibleTabs[i].route;
        if (r == '/' ? location == '/' : location.startsWith(r)) return i;
      }
      return 0;
    }();

    // Badge count for critical actions
    final actionsAsync = ref.watch(pendingActionsProvider);
    final criticalCount = actionsAsync.when(
      data: (actions) => actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length,
      loading: () => 0,
      error: (_, __) => 0,
    );

    Widget buildIcon(bool active, _NavTab tab) {
      final icon = Icon(active ? tab.activeIcon : tab.icon);
      if (tab.route != '/actions' || criticalCount == 0) return icon;
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
        type: BottomNavigationBarType.fixed,
        currentIndex: currentIndex,
        onTap: (index) => context.go(visibleTabs[index].route),
        items: visibleTabs.map((tab) => BottomNavigationBarItem(
          icon: buildIcon(false, tab),
          activeIcon: buildIcon(true, tab),
          label: tr(ref, tab.labelKey),
        )).toList(),
      ),
    );
  }
}
