import 'package:animations/animations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../features/auth/login_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/scan/scan_screen.dart';
import '../features/actions/actions_screen.dart';
import '../features/map/map_screen.dart';
import '../features/reports/reports_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/suppliers/suppliers_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/demo/demo_control_screen.dart';
import 'shell_scaffold.dart';

CustomTransitionPage<void> _sharedAxisPage(
  GoRouterState state,
  Widget child, {
  SharedAxisTransitionType axis = SharedAxisTransitionType.horizontal,
}) =>
    CustomTransitionPage<void>(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 280),
      transitionsBuilder: (context, animation, secondaryAnimation, child) =>
          SharedAxisTransition(
        animation: animation,
        secondaryAnimation: secondaryAnimation,
        transitionType: axis,
        child: child,
      ),
    );

CustomTransitionPage<void> _fadePage(GoRouterState state, Widget child) =>
    CustomTransitionPage<void>(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 220),
      transitionsBuilder: (context, animation, secondaryAnimation, child) =>
          FadeTransition(opacity: animation, child: child),
    );

/// Inicializado en main() desde SharedPreferences — solo controla la pantalla inicial.
final onboardingDoneProvider = Provider<bool>((ref) => true);

final routerProvider = Provider<GoRouter>((ref) {
  final onboardingDone = ref.watch(onboardingDoneProvider);

  return GoRouter(
    initialLocation: onboardingDone ? '/login' : '/onboarding',
    redirect: (context, state) {
      final loc = state.matchedLocation;

      // Onboarding: siempre accesible, nunca bloqueado
      if (loc == '/onboarding') return null;

      final session = Supabase.instance.client.auth.currentSession;
      final isLoggedIn = session != null;

      if (!isLoggedIn && loc != '/login') return '/login';
      if (isLoggedIn && loc == '/login') return '/';
      return null;
    },
    routes: [
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => ShellScaffold(child: child),
        routes: [
          GoRoute(
            path: '/',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const DashboardScreen(),
            ),
          ),
          GoRoute(
            path: '/scan',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const ScanScreen(),
            ),
          ),
          GoRoute(
            path: '/actions',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const ActionsScreen(),
            ),
          ),
          GoRoute(
            path: '/map',
            pageBuilder: (context, state) => _sharedAxisPage(
              state,
              MapScreen(initialPasillo: state.uri.queryParameters['pasillo']),
            ),
          ),
          GoRoute(
            path: '/reports',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const ReportsScreen(),
            ),
          ),
          GoRoute(
            path: '/profile',
            pageBuilder: (context, state) => _fadePage(
              state, const ProfileScreen(),
            ),
          ),
          GoRoute(
            path: '/suppliers',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const SuppliersScreen(),
            ),
          ),
          GoRoute(
            path: '/agents',
            redirect: (_, __) => '/',
          ),
          GoRoute(
            path: '/demo',
            pageBuilder: (context, state) => _fadePage(
              state, const DemoControlScreen(),
            ),
          ),
          GoRoute(
            path: '/chat',
            pageBuilder: (context, state) => _sharedAxisPage(
              state, const ChatScreen(), axis: SharedAxisTransitionType.vertical,
            ),
          ),
        ],
      ),
    ],
  );
});
