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

class MermaOpsApp extends ConsumerWidget {
  const MermaOpsApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
