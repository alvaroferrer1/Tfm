import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/actions/actions_provider.dart';
import 'l10n.dart';
import 'theme.dart';
import 'user_role_provider.dart';

class LangToggleButton extends ConsumerWidget {
  const LangToggleButton({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider);
    return TextButton(
      onPressed: () => ref.read(languageProvider.notifier).toggle(),
      style: TextButton.styleFrom(
        minimumSize: Size.zero,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(lang == 'es' ? 'EN' : 'ES',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
    );
  }
}

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
  _NavTab(route: '/',          icon: Icons.dashboard_outlined,          activeIcon: Icons.dashboard,               labelKey: 'nav_dashboard'),
  _NavTab(route: '/scan',      icon: Icons.qr_code_scanner_outlined,    activeIcon: Icons.qr_code_scanner,         labelKey: 'nav_scan'),
  _NavTab(route: '/actions',   icon: Icons.task_alt_outlined,           activeIcon: Icons.task_alt,                labelKey: 'nav_actions'),
  _NavTab(route: '/map',       icon: Icons.map_outlined,                activeIcon: Icons.map,                     labelKey: 'nav_map'),
  _NavTab(route: '/reports',   icon: Icons.bar_chart_outlined,          activeIcon: Icons.bar_chart,               labelKey: 'nav_reports',   minRole: UserRole.manager),
  _NavTab(route: '/suppliers', icon: Icons.local_shipping_outlined,     activeIcon: Icons.local_shipping,          labelKey: 'nav_suppliers', minRole: UserRole.manager),
  _NavTab(route: '/chat',      icon: Icons.chat_bubble_outline_rounded, activeIcon: Icons.chat_bubble_rounded,     labelKey: 'nav_chat'),
];

class ShellScaffold extends ConsumerStatefulWidget {
  final Widget child;
  const ShellScaffold({super.key, required this.child});

  @override
  ConsumerState<ShellScaffold> createState() => _ShellScaffoldState();
}

class _ShellScaffoldState extends ConsumerState<ShellScaffold> {
  final _seenIds = <String>{};
  bool _initialized = false;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;

    final roleAsync = ref.watch(userRoleProvider);
    final userRole = roleAsync.when(
      data: (r) => r,
      loading: () => UserRole.staff,
      error: (_, __) => UserRole.staff,
    );

    final visibleTabs = _allTabs.where((t) => userRole.index >= t.minRole.index).toList();

    final currentIndex = () {
      for (int i = 0; i < visibleTabs.length; i++) {
        final r = visibleTabs[i].route;
        if (r == '/' ? location == '/' : location.startsWith(r)) return i;
      }
      return 0;
    }();

    final actionsAsync = ref.watch(pendingActionsStreamProvider);
    final criticalCount = actionsAsync.when(
      data: (actions) => actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length,
      loading: () => 0,
      error: (_, __) => 0,
    );

    ref.listen<AsyncValue<List<Map<String, dynamic>>>>(
      pendingActionsStreamProvider,
      (_, next) {
        next.whenData((actions) {
          if (!_initialized) {
            _seenIds.addAll(actions.map((a) => a['id']?.toString() ?? ''));
            _initialized = true;
            return;
          }
          for (final a in actions) {
            final id = a['id']?.toString() ?? '';
            if (_seenIds.contains(id)) continue;
            _seenIds.add(id);
            final score = (a['priority_score'] as int?) ?? 0;
            final type = (a['action_type'] as String? ?? '').toUpperCase();
            if (score >= 85 || a['action_type'] == 'retirar') {
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  backgroundColor: const Color(0xFFDC2626),
                  duration: const Duration(seconds: 6),
                  content: Row(children: [
                    const Icon(Icons.warning_amber_rounded, color: Colors.white, size: 20),
                    const SizedBox(width: 10),
                    Expanded(child: Text(
                      'CRITICO — $type detectado (score $score/100)',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                    )),
                  ]),
                  action: SnackBarAction(
                    label: 'Ver',
                    textColor: Colors.white,
                    onPressed: () => GoRouter.of(context).go('/actions'),
                  ),
                ),
              );
            }
          }
        });
      },
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
      body: LayoutBuilder(builder: (ctx, constraints) {
        if (constraints.maxWidth <= 640) return widget.child;
        return Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: widget.child,
          ),
        );
      }),
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
