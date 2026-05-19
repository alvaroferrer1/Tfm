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

/// Se inicializa en main() leyendo SharedPreferences antes de runApp.
final onboardingDoneProvider = Provider<bool>((ref) => true);

final routerProvider = Provider<GoRouter>((ref) {
  final onboardingDone = ref.watch(onboardingDoneProvider);

  return GoRouter(
    initialLocation: onboardingDone ? '/login' : '/onboarding',
    redirect: (context, state) {
      final loc = state.matchedLocation;

      // Onboarding: bloquear todas las rutas hasta completarlo
      if (!onboardingDone && loc != '/onboarding') return '/onboarding';

      final session = Supabase.instance.client.auth.currentSession;
      final isLoggedIn = session != null;
      final isOnLogin = loc == '/login';
      final isOnOnboarding = loc == '/onboarding';

      if (isOnOnboarding) return null; // onboarding siempre accesible
      if (!isLoggedIn && !isOnLogin) return '/login';
      if (isLoggedIn && isOnLogin) return '/';
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
              // Deep link: mermaops://app/map?pasillo=A
              initialPasillo: state.uri.queryParameters['pasillo'],
            ),
          ),
          GoRoute(
            path: '/reports',
            builder: (context, state) => const ReportsScreen(),
          ),
          GoRoute(
            path: '/profile',
            // Deep link: mermaops://app/profile  (desde Telegram /start)
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
