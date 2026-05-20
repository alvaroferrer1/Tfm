import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_client.dart';

/// Servicio de notificaciones locales + Supabase Realtime.
///
/// No requiere FCM ni Firebase. Funciona en emulador y móvil real.
/// Escucha cambios en la tabla `actions` via Supabase Realtime y muestra
/// una notificación local cuando aparece una acción CRÍTICA nueva.
class NotificationService {
  static final _instance = NotificationService._();
  factory NotificationService() => _instance;
  NotificationService._();

  final _plugin = FlutterLocalNotificationsPlugin();
  RealtimeChannel? _actionsChannel;
  bool _initialized = false;

  static const _channelId = 'mermaops_alerts';
  static const _channelName = 'Alertas MermaOps';

  Future<void> init() async {
    if (_initialized) return;

    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: androidSettings);

    await _plugin.initialize(settings);

    // Solicitar permiso en Android 13+
    await _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();

    _initialized = true;
  }

  /// Suscribirse a la tabla actions via Supabase Realtime.
  /// Cuando aparece una acción INSERT con urgency='critico' o priority_score>=85
  /// → muestra notificación local inmediata.
  void subscribeToActions(String storeId) {
    _actionsChannel?.unsubscribe();
    _actionsChannel = supabase
        .channel('actions-realtime-$storeId')
        .onPostgresChanges(
          event: PostgresChangeEvent.insert,
          schema: 'public',
          table: 'actions',
          filter: PostgresChangeFilter(
            type: PostgresChangeFilterType.eq,
            column: 'store_id',
            value: storeId,
          ),
          callback: (payload) {
            final row = payload.newRecord;
            final score = (row['priority_score'] as int?) ?? 0;
            final actionType = row['action_type'] as String? ?? '';
            if (score >= 85 || actionType == 'retirar') {
              _showCriticalAlert(row);
            }
          },
        )
        .subscribe();
  }

  void unsubscribe() {
    _actionsChannel?.unsubscribe();
    _actionsChannel = null;
  }

  Future<void> _showCriticalAlert(Map<String, dynamic> action) async {
    final actionType = (action['action_type'] as String? ?? '').toUpperCase();
    final notes = action['notes'] as String? ?? 'Producto requiere atención inmediata';
    final score = action['priority_score'] as int? ?? 100;

    await _showNotification(
      id: DateTime.now().millisecondsSinceEpoch ~/ 1000,
      title: '🔴 CRÍTICO — $actionType detectado',
      body: '$notes (Score: $score/100)',
      importance: Importance.max,
    );
  }

  Future<void> showDemoAdvanceNotification(int days, int newCritical) async {
    if (!_initialized) await init();
    await _showNotification(
      id: 9001,
      title: '📅 Avanzados $days días — Kuine detectó $newCritical nuevos críticos',
      body: 'Revisa Acciones para ver los productos urgentes',
      importance: Importance.high,
    );
  }

  Future<void> showBriefReadyNotification() async {
    if (!_initialized) await init();
    await _showNotification(
      id: 9002,
      title: '📊 Brief diario listo',
      body: 'Kuine completó el análisis. Abre el dashboard para verlo.',
      importance: Importance.defaultImportance,
    );
  }

  Future<void> _showNotification({
    required int id,
    required String title,
    required String body,
    Importance importance = Importance.defaultImportance,
  }) async {
    if (!_initialized) return;
    try {
      final androidDetails = AndroidNotificationDetails(
        _channelId,
        _channelName,
        importance: importance,
        priority: importance == Importance.max ? Priority.high : Priority.defaultPriority,
        icon: '@mipmap/ic_launcher',
        styleInformation: BigTextStyleInformation(body),
      );
      final details = NotificationDetails(android: androidDetails);
      await _plugin.show(id, title, body, details);
    } catch (e) {
      debugPrint('[NotificationService] Error: $e');
    }
  }
}

final notifications = NotificationService();
