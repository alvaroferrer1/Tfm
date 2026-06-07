import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/notification_service.dart';
import '../../core/supabase_client.dart';
import '../../core/user_role_provider.dart';
import '../dashboard/dashboard_screen.dart' show dashboardProvider;
import '../actions/actions_provider.dart';

class DemoControlScreen extends ConsumerWidget {
  const DemoControlScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return RoleGate(
      requiredRole: UserRole.admin,
      child: const _DemoContent(),
    );
  }
}

class _DemoContent extends ConsumerStatefulWidget {
  const _DemoContent();

  @override
  ConsumerState<_DemoContent> createState() => _DemoControlScreenState();
}

class _DemoControlScreenState extends ConsumerState<_DemoContent> {
  int _daysToAdvance = 1;
  bool _loading = false;
  Map<String, dynamic>? _lastResult;
  Map<String, int>? _beforeState;
  Map<String, int>? _afterState;
  List<Map<String, dynamic>> _criticalProducts = [];

  Future<List<Map<String, dynamic>>> _fetchCriticalProducts() async {
    final data = await supabase
        .from('actions')
        .select('action_type, priority_score, batches(expiry_date, quantity, products(name, pasillo, estanteria, nivel))')
        .eq('store_id', storeId)
        .eq('status', 'pending')
        .gte('priority_score', 85)
        .order('priority_score', ascending: false)
        .limit(8);
    return List<Map<String, dynamic>>.from(data);
  }

  Future<Map<String, int>> _getCurrentState() async {
    final batches = await supabase
        .from('batches')
        .select('urgency')
        .eq('store_id', storeId)
        .eq('status', 'active');
    final counts = <String, int>{
      'caducado': 0,
      'critico': 0,
      'alto': 0,
      'normal': 0,
    };
    for (final b in batches) {
      final u = (b['urgency'] as String? ?? 'normal').toLowerCase();
      counts[u] = (counts[u] ?? 0) + 1;
    }
    return counts;
  }

  Future<void> _advance() async {
    setState(() { _loading = true; _lastResult = null; });
    try {
      final before = await _getCurrentState();
      final result = await api.advanceDemo(days: _daysToAdvance);
      final after = await _getCurrentState();
      final critical = await _fetchCriticalProducts();

      final newCritical = (after['critico'] ?? 0) - (before['critico'] ?? 0);
      if (newCritical > 0) {
        await notifications.showDemoAdvanceNotification(_daysToAdvance, newCritical);
      }

      ref.invalidate(dashboardProvider);
      ref.invalidate(pendingActionsProvider);
      ref.invalidate(completedActionsProvider);

      setState(() {
        _lastResult = result;
        _beforeState = before;
        _afterState = after;
        _criticalProducts = critical;
        _loading = false;
      });
    } catch (e) {
      setState(() { _loading = false; });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(friendlyError(e)), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _reset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Resetear demo'),
        content: Text(
          'Vuelve al estado inicial de $storeName.\n¿Continuar?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Resetear'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    setState(() { _loading = true; });
    try {
      await api.resetDemo();
      final after = await _getCurrentState();
      final critical = await _fetchCriticalProducts();
      ref.invalidate(dashboardProvider);
      ref.invalidate(pendingActionsProvider);
      ref.invalidate(completedActionsProvider);
      setState(() {
        _afterState = after;
        _beforeState = null;
        _criticalProducts = critical;
        _lastResult = {'ok': true, 'summary': {'estado': 'reiniciado'}};
        _loading = false;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Demo reiniciada al estado inicial'),
            backgroundColor: Color(0xFF059669),
          ),
        );
      }
    } catch (e) {
      setState(() { _loading = false; });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(friendlyError(e)), backgroundColor: Colors.red),
        );
      }
    }
  }

  Widget _urgencyRow(String label, Color color, int? before, int? after) {
    final b = before ?? 0;
    final a = after ?? 0;
    final diff = a - b;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        Container(
          width: 12, height: 12,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 80, child: Text(label, style: const TextStyle(fontSize: 13))),
        if (before != null) ...[
          Text('$b', style: const TextStyle(fontSize: 13, color: Colors.grey)),
          const SizedBox(width: 8),
          const Icon(Icons.arrow_forward, size: 14, color: Colors.grey),
          const SizedBox(width: 8),
        ],
        Text('$a',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.bold,
              color: diff > 0 ? Colors.red : diff < 0 ? Colors.green : null,
            )),
        if (before != null && diff != 0) ...[
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: (diff > 0 ? Colors.red : Colors.green).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              '${diff > 0 ? '+' : ''}$diff',
              style: TextStyle(
                fontSize: 10,
                color: diff > 0 ? Colors.red : Colors.green,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Control Demo'),
        centerTitle: true,
        backgroundColor: const Color(0xFF1E1E2E),
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header info
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF1E1E2E), Color(0xFF2D1B69)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(children: [
                    Icon(Icons.science, color: Colors.white, size: 20),
                    SizedBox(width: 8),
                    Text('Simulador temporal',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 16)),
                  ]),
                  const SizedBox(height: 8),
                  const Text(
                    'Avanza días en la base de datos para mostrar cómo evoluciona la merma. '
                    'Los productos se acercan a su caducidad y aparecen nuevas alertas.',
                    style: TextStyle(color: Colors.white70, fontSize: 13, height: 1.5),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Days selector
            Text('Días a avanzar', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [1, 2, 3, 5, 7, 10].map((d) => GestureDetector(
                onTap: () => setState(() => _daysToAdvance = d),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    color: _daysToAdvance == d
                        ? const Color(0xFF7C3AED)
                        : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: _daysToAdvance == d
                          ? const Color(0xFF7C3AED)
                          : Colors.grey.shade300,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      '+$d',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: _daysToAdvance == d ? Colors.white : Colors.grey.shade700,
                      ),
                    ),
                  ),
                ),
              )).toList(),
            ),

            const SizedBox(height: 24),

            // Action buttons
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _loading ? null : _advance,
                icon: _loading
                    ? const SizedBox(
                        width: 16, height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.fast_forward),
                label: Text(_loading
                    ? 'Avanzando...'
                    : 'Avanzar $_daysToAdvance día${_daysToAdvance > 1 ? 's' : ''}'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF7C3AED),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _loading ? null : _reset,
                icon: const Icon(Icons.restore, color: Colors.red),
                label: const Text('Resetear al estado inicial',
                    style: TextStyle(color: Colors.red)),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.red),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),

            // Before / After comparison
            if (_afterState != null) ...[
              const SizedBox(height: 28),
              Text('Estado de la tienda',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (_beforeState != null) ...[
                        Row(children: [
                          Text('Antes', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                          const SizedBox(width: 32),
                          const Icon(Icons.arrow_forward, size: 14, color: Colors.grey),
                          const SizedBox(width: 8),
                          const Text('Después',
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                        ]),
                        const Divider(height: 16),
                      ],
                      _urgencyRow('Caducado', Colors.red.shade800,
                          _beforeState?['caducado'], _afterState!['caducado']),
                      _urgencyRow('Crítico', Colors.red,
                          _beforeState?['critico'], _afterState!['critico']),
                      _urgencyRow('Alto', Colors.orange,
                          _beforeState?['alto'], _afterState!['alto']),
                      _urgencyRow('Normal', Colors.green,
                          _beforeState?['normal'], _afterState!['normal']),
                    ],
                  ),
                ),
              ),
            ],

            // Productos críticos actuales
            if (_criticalProducts.isNotEmpty) ...[
              const SizedBox(height: 20),
              Text('Productos críticos ahora',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 10),
              ..._criticalProducts.map((action) {
                final batch = action['batches'] as Map<String, dynamic>?;
                final product = batch?['products'] as Map<String, dynamic>?;
                final name = product?['name'] as String? ?? 'Producto';
                final pasillo = product?['pasillo'] as String? ?? '?';
                final est = product?['estanteria'] as String? ?? '?';
                final nivel = product?['nivel'] as String? ?? '?';
                final expiry = batch?['expiry_date'] as String? ?? '';
                final qty = batch?['quantity'] as int? ?? 0;
                final score = action['priority_score'] as int? ?? 0;
                final actionType = (action['action_type'] as String? ?? '').toUpperCase();
                int daysLeft = 999;
                try {
                  daysLeft = DateTime.parse(expiry).difference(DateTime.now()).inDays;
                } catch (_) {}
                final urgencyColor = daysLeft <= 0
                    ? Colors.red.shade900
                    : daysLeft <= 2
                        ? Colors.red
                        : Colors.orange;
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: urgencyColor.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: urgencyColor.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 6, height: 40,
                        decoration: BoxDecoration(
                          color: urgencyColor,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(name,
                                style: const TextStyle(
                                    fontSize: 13, fontWeight: FontWeight.w700)),
                            const SizedBox(height: 2),
                            Text(
                              'Pasillo $pasillo — E$est N$nivel | $qty uds',
                              style: const TextStyle(fontSize: 11, color: Colors.grey),
                            ),
                            Text(
                              daysLeft <= 0
                                  ? 'Caducado'
                                  : daysLeft == 1
                                      ? 'Caduca mañana'
                                      : 'Caduca en $daysLeft días',
                              style: TextStyle(
                                  fontSize: 11,
                                  color: urgencyColor,
                                  fontWeight: FontWeight.w600),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: urgencyColor.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              actionType,
                              style: TextStyle(
                                  fontSize: 10,
                                  color: urgencyColor,
                                  fontWeight: FontWeight.w700),
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text('$score/100',
                              style: TextStyle(
                                  fontSize: 11,
                                  color: urgencyColor,
                                  fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ],
                  ),
                );
              }),
            ],

            // Summary from API
            if (_lastResult != null && _lastResult!['summary'] != null) ...[
              const SizedBox(height: 16),
              Card(
                color: Colors.green.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(children: [
                        Icon(Icons.check_circle, color: Colors.green, size: 18),
                        SizedBox(width: 6),
                        Text('Resumen del avance',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                      ]),
                      const SizedBox(height: 8),
                      ...((_lastResult!['summary'] as Map<String, dynamic>)
                          .entries
                          .map((e) => Padding(
                                padding: const EdgeInsets.only(bottom: 3),
                                child: Text(
                                  '${e.key.replaceAll('_', ' ')}: ${e.value}',
                                  style: const TextStyle(fontSize: 13),
                                ),
                              ))),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              // Botón para ir al dashboard y ver los cambios en tiempo real
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: () => context.go('/'),
                  icon: const Icon(Icons.dashboard),
                  label: const Text('Ver cambios en Dashboard'),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF059669),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => context.go('/actions'),
                  icon: const Icon(Icons.warning_amber_outlined),
                  label: const Text('Ver Acciones urgentes'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.orange,
                    side: const BorderSide(color: Colors.orange),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ],

            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}
