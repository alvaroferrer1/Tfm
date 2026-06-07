import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'core/notification_service.dart';
import 'core/router.dart' show routerProvider, onboardingDoneProvider;
import 'core/supabase_client.dart';
import 'core/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final prefs = await SharedPreferences.getInstance();
  final onboardingDone = prefs.getBool('onboarding_done') ?? false;

  await Supabase.initialize(
    url: const String.fromEnvironment(
      'SUPABASE_URL',
      defaultValue: 'https://YOUR_PROJECT.supabase.co',
    ),
    anonKey: const String.fromEnvironment(
      'SUPABASE_ANON_KEY',
      defaultValue: 'YOUR_ANON_KEY',
    ),
  );

  // Inicializar notificaciones locales
  await notifications.init();

  // Suscribirse a alertas cuando el usuario esté autenticado
  Supabase.instance.client.auth.onAuthStateChange.listen((data) {
    if (data.session != null) {
      notifications.subscribeToActions(storeId);
    } else {
      notifications.unsubscribe();
    }
  });

  runApp(ProviderScope(
    overrides: [onboardingDoneProvider.overrideWithValue(onboardingDone)],
    child: const MermaOpsApp(),
  ));
}

// ── App lifecycle observer — flushes offline queue on foreground ─────────────
class _AppLifecycleObserver extends WidgetsBindingObserver {
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // App vuelve al primer plano — intentar sincronizar acciones offline
      // No necesita WidgetRef porque opera directamente sobre Supabase
      _trySyncOfflineActions();
    }
  }

  Future<void> _trySyncOfflineActions() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getStringList('offline_actions_queue') ?? [];
      if (raw.isEmpty) return;

      final remaining = <String>[];
      for (final item in raw) {
        final parts = item.split('|');
        if (parts.length < 2) continue;
        final actionId = parts[0];
        final userId = parts[1];
        final notes = parts.length > 2 ? Uri.decodeComponent(parts[2]) : '';
        try {
          await Supabase.instance.client.from('actions').update({
            'status': 'completed',
            'completed_by': userId,
            'completed_at': DateTime.now().toUtc().toIso8601String(),
            'notes': notes,
          }).eq('id', actionId);
        } catch (_) {
          remaining.add(item);
        }
      }
      await prefs.setStringList('offline_actions_queue', remaining);
    } catch (_) {}
  }
}

class MermaOpsApp extends ConsumerStatefulWidget {
  const MermaOpsApp({super.key});

  @override
  ConsumerState<MermaOpsApp> createState() => _MermaOpsAppState();
}

class _MermaOpsAppState extends ConsumerState<MermaOpsApp> {
  final _lifecycleObserver = _AppLifecycleObserver();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(_lifecycleObserver);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(_lifecycleObserver);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'MermaOps',
      theme: appTheme,
      darkTheme: appDarkTheme,
      themeMode: ThemeMode.system,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
