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
import '../features/agents/agents_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import 'shell_scaffold.dart';

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
            builder: (context, state) => const DashboardScreen(),
          ),
          GoRoute(
            path: '/scan',
            builder: (context, state) => const ScanScreen(),
          ),
          GoRoute(
            path: '/actions',
            builder: (context, state) => const ActionsScreen(),
          ),
          GoRoute(
            path: '/map',
            builder: (context, state) => MapScreen(
              initialPasillo: state.uri.queryParameters['pasillo'],
            ),
          ),
          GoRoute(
            path: '/reports',
            builder: (context, state) => const ReportsScreen(),
          ),
          GoRoute(
            path: '/profile',
            builder: (context, state) => const ProfileScreen(),
          ),
          GoRoute(
            path: '/agents',
            builder: (context, state) => const AgentsScreen(),
          ),
        ],
      ),
    ],
  );
});
