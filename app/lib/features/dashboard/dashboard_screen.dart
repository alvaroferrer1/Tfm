import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_service.dart';
import '../../core/l10n.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';

// ── Providers ────────────────────────────────────────────────────────────────

final _comparisonProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getStoresComparison();
});

final dashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final pending = await supabase
      .from('actions')
      .select('priority_score')
      .eq('store_id', storeId)
      .eq('status', 'pending');

  final batches = await supabase
      .from('batches')
      .select('quantity, products(price)')
      .eq('store_id', storeId)
      .eq('status', 'active')
      .lte('expiry_date',
          DateTime.now().add(const Duration(days: 7)).toIso8601String().substring(0, 10));

  final brief = await supabase
      .from('daily_briefs')
      .select()
      .eq('store_id', storeId)
      .order('date', ascending: false)
      .limit(1)
      .maybeSingle();

  double valueAtRisk = 0;
  for (final b in batches) {
    final qty = (b['quantity'] as num?)?.toDouble() ?? 0;
    final price = ((b['products'] as Map?)?['price'] as num?)?.toDouble() ?? 0;
    valueAtRisk += qty * price;
  }

  final pendingList = List<Map<String, dynamic>>.from(pending);
  final criticalCount =
      pendingList.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length;

  // Donation stats for social impact card
  final donationsRaw = await supabase
      .from('donations')
      .select('quantity, value_donated, entity')
      .eq('store_id', storeId)
      .gte('donated_at',
          DateTime.now().subtract(const Duration(days: 30)).toIso8601String());
  final donations = List<Map<String, dynamic>>.from(donationsRaw);
  final donationQty = donations.fold<int>(0, (s, d) => s + ((d['quantity'] as int?) ?? 0));
  final donationValue = donations.fold<double>(
      0, (s, d) => s + ((d['value_donated'] as num?)?.toDouble() ?? 0));

  // Last 7 days merma for sparkline
  final cutoff7 = DateTime.now().subtract(const Duration(days: 7));
  final merma7 = await supabase
      .from('merma_log')
      .select('date, value_lost')
      .eq('store_id', storeId)
      .gte('date', cutoff7.toIso8601String().substring(0, 10))
      .order('date', ascending: true);

  return {
    'pending_count': pendingList.length,
    'critical_count': criticalCount,
    'value_at_risk': valueAtRisk,
    'brief': brief,
    'expiring_count': batches.length,
    'merma_7d': List<Map<String, dynamic>>.from(merma7),
    'donation_qty': donationQty,
    'donation_value': donationValue,
  };
});

// ── Screen ────────────────────────────────────────────────────────────────────

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashAsync = ref.watch(dashboardProvider);
    final user = supabase.auth.currentUser;
    final lang = ref.watch(languageProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF0FDF4),
      appBar: AppBar(
        title: const Text('MermaOps'),
        actions: [
          TextButton(
            onPressed: () => ref.read(languageProvider.notifier).toggle(),
            child: Text(
              lang == 'es' ? 'EN' : 'ES',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.refresh_outlined),
            onPressed: () => ref.invalidate(dashboardProvider),
            tooltip: tr(ref, 'refresh'),
          ),
          IconButton(
            icon: const Icon(Icons.person_outline),
            onPressed: () => context.go('/profile'),
            tooltip: 'Mi perfil',
          ),
        ],
      ),
      body: dashAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              Text('No se pudo conectar: $e', textAlign: TextAlign.center),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => ref.invalidate(dashboardProvider),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
        data: (data) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(dashboardProvider),
          child: _DashboardBody(data: data, userEmail: user?.email),
        ),
      ),
    );
  }
}

class _DashboardBody extends ConsumerWidget {
  final Map<String, dynamic> data;
  final String? userEmail;

  const _DashboardBody({required this.data, this.userEmail});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pending = data['pending_count'] as int? ?? 0;
    final critical = data['critical_count'] as int? ?? 0;
    final valueAtRisk = (data['value_at_risk'] as double? ?? 0);
    final expiring = data['expiring_count'] as int? ?? 0;
    final brief = data['brief'] as Map<String, dynamic>?;
    final merma7d = List<Map<String, dynamic>>.from(data['merma_7d'] as List? ?? []);
    final donationQty = data['donation_qty'] as int? ?? 0;
    final donationValue = (data['donation_value'] as double? ?? 0);

    return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Greeting
          Text(
            'Hola ${userEmail?.split('@').first ?? 'empleado'}',
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),
          Text(
            _dateLabel(),
            style: TextStyle(fontSize: 13, color: Colors.grey[600]),
          ),
          const SizedBox(height: 20),

          // KPI grid — siempre 2 columnas, las tarjetas se adaptan al ancho
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _KpiCard(
                  label: tr(ref, 'pending_actions'),
                  value: '$pending',
                  icon: Icons.task_alt,
                  color: pending > 0 ? UrgencyColors.high : UrgencyColors.low,
                  onTap: () => context.go('/actions'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _KpiCard(
                  label: tr(ref, 'critical_now'),
                  value: '$critical',
                  icon: Icons.warning_amber,
                  color: critical > 0 ? UrgencyColors.critical : UrgencyColors.low,
                  onTap: () => context.go('/actions'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _KpiCard(
                  label: tr(ref, 'value_at_risk'),
                  value: '${valueAtRisk.toStringAsFixed(0)} €',
                  icon: Icons.euro,
                  color: valueAtRisk > 50 ? UrgencyColors.high : UrgencyColors.low,
                  onTap: () => context.go('/reports'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _KpiCard(
                  label: tr(ref, 'expiring_7d'),
                  value: '$expiring',
                  icon: Icons.schedule,
                  color: UrgencyColors.medium,
                  onTap: () => context.go('/map'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Quick actions — 4 en fila en tablets/landscape, 2x2 en móvil pequeño
          Text(
            tr(ref, 'quick_actions'),
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 360;
              final actions = [
                _QuickAction(
                  icon: Icons.qr_code_scanner,
                  label: tr(ref, 'scan_product'),
                  color: const Color(0xFF059669),
                  onTap: () => context.go('/scan'),
                ),
                _QuickAction(
                  icon: Icons.map_outlined,
                  label: tr(ref, 'daily_route'),
                  color: const Color(0xFF3B82F6),
                  onTap: () => context.go('/map'),
                ),
                _QuickAction(
                  icon: Icons.bar_chart,
                  label: tr(ref, 'nav_reports'),
                  color: const Color(0xFF8B5CF6),
                  onTap: () => context.go('/reports'),
                ),
                _QuickAction(
                  icon: Icons.auto_awesome,
                  label: tr(ref, 'generate_brief'),
                  color: const Color(0xFFF59E0B),
                  onTap: () => _runBrief(context, ref),
                ),
              ];
              if (wide) {
                return Row(
                  children: actions
                      .expand((a) => [Expanded(child: a), const SizedBox(width: 8)])
                      .toList()
                    ..removeLast(),
                );
              }
              return Column(
                children: [
                  Row(
                    children: [
                      Expanded(child: actions[0]),
                      const SizedBox(width: 8),
                      Expanded(child: actions[1]),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(child: actions[2]),
                      const SizedBox(width: 8),
                      Expanded(child: actions[3]),
                    ],
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 24),

          // Merma 7d sparkline
          if (merma7d.isNotEmpty) ...[
            _MermaSparkline(logs: merma7d),
            const SizedBox(height: 24),
          ],

          // Social impact card — only if there are donations
          if (donationQty > 0) ...[
            _DonationImpactCard(qty: donationQty, value: donationValue),
            const SizedBox(height: 24),
          ],

          // Stores comparison (Feature #15)
          const _StoresComparisonCard(),
          const SizedBox(height: 24),

          // Brief del día
          if (brief != null) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Brief del día',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
                Text(
                  brief['date'] ?? '',
                  style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFD1FAE5)),
              ),
              child: Text(
                brief['summary'] ?? 'Sin resumen disponible',
                style: const TextStyle(fontSize: 13, height: 1.5),
                maxLines: 6,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: () => context.go('/reports'),
              icon: const Icon(Icons.arrow_forward, size: 16),
              label: const Text('Ver informe completo'),
            ),
          ] else ...[
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFFFFBEB),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFFDE68A)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, color: Color(0xFFD97706)),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'No hay brief para hoy. Se genera automáticamente a las 07:30 o puedes pedirle a Chuwi en Telegram.',
                      style: TextStyle(fontSize: 13, color: Color(0xFF92400E)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
    );
  }

  void _runBrief(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);

    // Mostrar spinner — el endpoint devuelve inmediatamente, el brief se genera en background
    messenger.showSnackBar(
      const SnackBar(
        content: Row(children: [
          SizedBox(
            width: 16, height: 16,
            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
          ),
          SizedBox(width: 12),
          Expanded(child: Text('Generando brief con IA… (30–90 segundos)')),
        ]),
        duration: Duration(seconds: 120),
        backgroundColor: Color(0xFFF59E0B),
      ),
    );

    try {
      // Lanzar generación en background
      await api.runBrief();

      // Escuchar via Supabase realtime hasta que el brief aparezca en BD
      final today = DateTime.now().toIso8601String().substring(0, 10);
      bool found = false;

      // Polling cada 5s durante máx 90s (brief puede tardar hasta 60s)
      for (int attempt = 0; attempt < 18 && !found; attempt++) {
        await Future.delayed(const Duration(seconds: 5));
        try {
          final result = await supabase
              .from('daily_briefs')
              .select('id')
              .eq('store_id', storeId)
              .eq('date', today)
              .maybeSingle();
          if (result != null) found = true;
        } catch (_) {}
      }

      messenger.hideCurrentSnackBar();

      if (found) {
        ref.invalidate(dashboardProvider);
        messenger.showSnackBar(
          const SnackBar(
            content: Text('Brief generado. Dashboard actualizado.'),
            backgroundColor: Color(0xFF059669),
            duration: Duration(seconds: 4),
          ),
        );
      } else {
        messenger.showSnackBar(
          const SnackBar(
            content: Text('Brief en proceso. Actualiza el dashboard en un minuto.'),
            backgroundColor: Color(0xFFF59E0B),
            duration: Duration(seconds: 5),
          ),
        );
      }
    } catch (e) {
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(
        SnackBar(
          content: Text('Error al generar el brief: $e'),
          backgroundColor: const Color(0xFFEF4444),
          duration: const Duration(seconds: 5),
        ),
      );
    }
  }

  String _dateLabel() {
    final now = DateTime.now();
    final weekdays = [
      'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'
    ];
    final months = [
      '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
      'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ];
    return '${weekdays[now.weekday - 1]}, ${now.day} de ${months[now.month]}';
  }
}

class _StoresComparisonCard extends ConsumerWidget {
  const _StoresComparisonCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_comparisonProvider);
    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (stores) {
        if (stores.isEmpty) return const SizedBox.shrink();
        final current = stores.firstWhere(
          (s) => s['is_current'] == true,
          orElse: () => stores.first,
        );
        final currentRank = current['rank'] as int? ?? 0;
        final total = stores.length;
        final maxMerma = stores.fold<double>(
          0, (m, s) => ((s['merma_rate_pct'] as num?)?.toDouble() ?? 0) > m
              ? (s['merma_rate_pct'] as num).toDouble()
              : m,
        );

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.emoji_events,
                      color: Color(0xFFF59E0B), size: 20),
                  const SizedBox(width: 6),
                  const Expanded(
                    child: Text(
                      'Comparativa de tiendas',
                      style: TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w700),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: currentRank == 1
                          ? const Color(0xFFD1FAE5)
                          : currentRank <= 2
                              ? const Color(0xFFEFF6FF)
                              : const Color(0xFFFEE2E2),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'Puesto $currentRank de $total',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: currentRank == 1
                            ? const Color(0xFF059669)
                            : currentRank <= 2
                                ? const Color(0xFF2563EB)
                                : const Color(0xFFDC2626),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ...stores.map((s) {
                final name = s['store_name'] as String? ?? '';
                final merma =
                    (s['merma_rate_pct'] as num?)?.toDouble() ?? 0;
                final isCurrent = s['is_current'] == true;
                final rank = s['rank'] as int? ?? 0;
                final ratio = maxMerma > 0 ? merma / maxMerma : 0.0;

                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 18,
                        child: Text(
                          rank == 1 ? '🥇' : '$rank.',
                          style: const TextStyle(fontSize: 11),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        flex: 3,
                        child: Text(
                          name,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: isCurrent
                                ? FontWeight.w700
                                : FontWeight.normal,
                            color: isCurrent
                                ? const Color(0xFF059669)
                                : Colors.black87,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 4,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(3),
                          child: LinearProgressIndicator(
                            value: ratio,
                            minHeight: 6,
                            backgroundColor: const Color(0xFFF3F4F6),
                            valueColor: AlwaysStoppedAnimation<Color>(
                              isCurrent
                                  ? const Color(0xFF059669)
                                  : const Color(0xFF9CA3AF),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${merma.toStringAsFixed(1)}%',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: isCurrent
                              ? FontWeight.w700
                              : FontWeight.normal,
                          color: isCurrent
                              ? const Color(0xFF059669)
                              : Colors.grey,
                        ),
                      ),
                    ],
                  ),
                );
              }),
              const SizedBox(height: 4),
              const Text(
                'Tasa de merma sobre ventas. Menor es mejor.',
                style: TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _DonationImpactCard extends StatelessWidget {
  final int qty;
  final double value;

  const _DonationImpactCard({required this.qty, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF059669), Color(0xFF10B981)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Icon(Icons.volunteer_activism, color: Colors.white, size: 32),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Impacto social este mes',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '$qty unidades donadas',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text(
                  '${value.toStringAsFixed(2)} € de valor donado',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Text(
              '♻ Reducción merma',
              style: TextStyle(
                color: Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MermaSparkline extends StatelessWidget {
  final List<Map<String, dynamic>> logs;

  const _MermaSparkline({required this.logs});

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final days = List.generate(7, (i) => now.subtract(Duration(days: 6 - i)));

    final Map<String, double> byDate = {};
    for (final log in logs) {
      final date = log['date'] as String? ?? '';
      byDate[date] = (byDate[date] ?? 0) + ((log['value_lost'] as num?)?.toDouble() ?? 0);
    }

    final values = days
        .map((d) => byDate[d.toIso8601String().substring(0, 10)] ?? 0.0)
        .toList();
    final total7d = values.fold(0.0, (a, b) => a + b);
    final maxVal = values.fold(0.0, (a, b) => b > a ? b : a);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Merma últimos 7 días',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              Text(
                '${total7d.toStringAsFixed(2)} €',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFFEF4444),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 44,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: List.generate(7, (i) {
                final ratio = maxVal > 0 ? values[i] / maxVal : 0.0;
                final isToday = i == 6;
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        AnimatedContainer(
                          duration: Duration(milliseconds: 250 + i * 40),
                          curve: Curves.easeOut,
                          height: values[i] > 0 ? (4 + ratio * 36) : 3,
                          decoration: BoxDecoration(
                            color: isToday
                                ? const Color(0xFFEF4444)
                                : values[i] > 0
                                    ? const Color(0xFFFCA5A5)
                                    : const Color(0xFFF3F4F6),
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _dayLabel(days[i]),
                          style: TextStyle(
                            fontSize: 9,
                            color: isToday
                                ? const Color(0xFFEF4444)
                                : Colors.grey,
                            fontWeight: isToday
                                ? FontWeight.w700
                                : FontWeight.normal,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ],
      ),
    );
  }

  String _dayLabel(DateTime d) {
    const labels = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
    return labels[d.weekday - 1];
  }
}

class _KpiCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  const _KpiCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.1),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 8),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                value,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  color: color,
                  letterSpacing: -1,
                ),
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(fontSize: 11, color: Colors.grey[600], height: 1.3),
            ),
          ],
        ),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _QuickAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(height: 6),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11,
                color: color,
                fontWeight: FontWeight.w600,
                height: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
