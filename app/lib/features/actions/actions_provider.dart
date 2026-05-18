import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/supabase_client.dart';

// FutureProvider para carga inicial
final pendingActionsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final data = await supabase
      .from('actions')
      .select('*, batches(*, products(*))')
      .eq('store_id', storeId)
      .eq('status', 'pending')
      .order('priority_score', ascending: false);
  return List<Map<String, dynamic>>.from(data);
});

// StreamProvider para actualizaciones en tiempo real
final pendingActionsStreamProvider = StreamProvider<List<Map<String, dynamic>>>((ref) {
  return supabase
      .from('actions')
      .stream(primaryKey: ['id'])
      .eq('store_id', storeId)
      .order('priority_score', ascending: false)
      .map((data) => data
          .where((a) => a['status'] == 'pending')
          .toList()
          .cast<Map<String, dynamic>>());
});

// Historial de acciones completadas (últimos 30 días) para trazabilidad por empleado
final completedActionsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final cutoff = DateTime.now().subtract(const Duration(days: 30));
  final data = await supabase
      .from('actions')
      .select('*, batches(*, products(*))')
      .eq('store_id', storeId)
      .eq('status', 'completed')
      .gte('completed_at', cutoff.toIso8601String())
      .order('completed_at', ascending: false)
      .limit(100);
  return List<Map<String, dynamic>>.from(data);
});
