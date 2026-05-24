import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:file_picker/file_picker.dart';

import '../../core/api_service.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';
import '../../core/user_role_provider.dart';

import 'dart:io' show File;

final _dailyBriefsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getDailyBriefsList(limit: 14);
});

final _weeklyReportsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final data = await supabase
      .from('weekly_reports')
      .select()
      .eq('store_id', storeId)
      .order('week_start', ascending: false)
      .limit(8);
  return List<Map<String, dynamic>>.from(data);
});

final _monthlyReportsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final data = await supabase
      .from('monthly_reports')
      .select()
      .eq('store_id', storeId)
      .order('month', ascending: false)
      .limit(6);
  return List<Map<String, dynamic>>.from(data);
});

final _suppliersProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getSupplierStats();
});

final _mermaHistoryProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final cutoff = DateTime.now().subtract(const Duration(days: 30));
  final data = await supabase
      .from('merma_log')
      .select()
      .eq('store_id', storeId)
      .gte('date', cutoff.toIso8601String().substring(0, 10))
      .order('date', ascending: false);
  return List<Map<String, dynamic>>.from(data);
});

final _orderSuggestionsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getOrderSuggestions();
});

class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return RoleGate(
      requiredRole: UserRole.manager,
      child: const _ReportsContent(),
    );
  }
}

class _ReportsContent extends ConsumerStatefulWidget {
  const _ReportsContent();

  @override
  ConsumerState<_ReportsContent> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends ConsumerState<_ReportsContent>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 9, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Informes'),
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(text: 'Diarios'),
            Tab(text: 'Semanales'),
            Tab(text: 'Mensual'),
            Tab(text: 'Merma'),
            Tab(text: 'Proveedores'),
            Tab(text: 'Pedidos'),
            Tab(text: 'ESG 🌱'),
            Tab(text: 'Predicciones 🔮'),
            Tab(text: 'Analizar PDF 🤖'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          const _DailyBriefsTab(),
          const _WeeklyReportsTab(),
          const _MonthlyReportsTab(),
          const _MermaTab(),
          const _SuppliersTab(),
          const _OrderSuggestionsTab(),
          const _EsgTab(),
          const _PredictionsTab(),
          const _AnalyzePdfTab(),
        ],
      ),
    );
  }
}

class _DailyBriefsTab extends ConsumerWidget {
  const _DailyBriefsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_dailyBriefsProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
      data: (briefs) {
        if (briefs.isEmpty) {
          return const Center(child: Text('Sin briefs disponibles aún'));
        }
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: briefs.length,
          itemBuilder: (context, i) {
            final brief = briefs[i];
            final date = brief['date'] as String? ?? '';
            final summary = brief['summary'] as String? ?? '';
            final value = (brief['value_at_risk'] as num?)?.toDouble() ?? 0;
            final actionsCount = brief['actions_count'] as int? ?? 0;
            final isToday = date == DateTime.now().toIso8601String().substring(0, 10);

            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ExpansionTile(
                tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                title: Row(
                  children: [
                    Text(
                      date,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: isToday ? const Color(0xFF059669) : null,
                      ),
                    ),
                    if (isToday) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFFD1FAE5),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'Hoy',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF059669),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                subtitle: Text(
                  '$actionsCount acciones — ${value.toStringAsFixed(0)} € en riesgo',
                  style: const TextStyle(fontSize: 12),
                ),
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      summary,
                      style: const TextStyle(fontSize: 13, height: 1.6),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: _PdfDownloadButton(
                      label: '📄 Descargar PDF',
                      filename: 'brief_$date.pdf',
                      download: () => api.downloadBriefPdf(date: date),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _WeeklyReportsTab extends ConsumerWidget {
  const _WeeklyReportsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_weeklyReportsProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
      data: (reports) {
        if (reports.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.bar_chart, size: 48, color: Colors.grey),
                  SizedBox(height: 12),
                  Text(
                    'Sin informes semanales aún',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Los informes se generan automáticamente cada lunes a las 06:00',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: reports.length,
          itemBuilder: (context, i) {
            final report = reports[i];
            final week = report['week_start'] as String? ?? '';
            final content = report['content'] as String? ?? '';
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ExpansionTile(
                title: Text(
                  'Semana del $week',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      content,
                      style: const TextStyle(fontSize: 13, height: 1.6),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: _PdfDownloadButton(
                      label: '📊 Descargar PDF semanal',
                      filename: 'informe_semanal_$week.pdf',
                      download: () => api.downloadWeeklyPdf(weekStart: week),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _MonthlyReportsTab extends ConsumerWidget {
  const _MonthlyReportsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_monthlyReportsProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
      data: (reports) {
        if (reports.isEmpty) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.summarize_outlined, size: 48, color: Colors.grey),
                  const SizedBox(height: 12),
                  const Text(
                    'Sin informes mensuales aún',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Los informes para el dueño se generan el día 1 de cada mes a las 08:00.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Generar ahora'),
                    onPressed: () async {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Generando informe mensual con IA…'),
                          duration: Duration(seconds: 90),
                        ),
                      );
                      try {
                        await api.runMonthlyReport();
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).hideCurrentSnackBar();
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Informe mensual en proceso. Actualiza en un momento.'),
                              backgroundColor: Color(0xFF059669),
                            ),
                          );
                          ref.invalidate(_monthlyReportsProvider);
                        }
                      } catch (e) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).hideCurrentSnackBar();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Error: $e'),
                              backgroundColor: Colors.red,
                            ),
                          );
                        }
                      }
                    },
                  ),
                ],
              ),
            ),
          );
        }

        return ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: reports.length,
          itemBuilder: (context, i) {
            final report = reports[i];
            final month = report['month'] as String? ?? '';
            final content = report['content'] as String? ?? '';
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: ExpansionTile(
                leading: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFF7C3AED).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(
                    Icons.summarize,
                    size: 18,
                    color: Color(0xFF7C3AED),
                  ),
                ),
                title: Text(
                  'Informe mensual — $month',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: const Text(
                  'Para el dueño',
                  style: TextStyle(fontSize: 11, color: Color(0xFF7C3AED)),
                ),
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                    child: Text(
                      content,
                      style: const TextStyle(fontSize: 13, height: 1.6),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: _PdfDownloadButton(
                      label: '📈 Descargar PDF mensual',
                      filename: 'informe_mensual_$month.pdf',
                      download: () => api.downloadMonthlyPdf(),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _MermaTab extends ConsumerWidget {
  const _MermaTab();

  static Future<void> _exportCsv(BuildContext context, List<Map<String, dynamic>> logs) async {
    final lines = <String>['fecha,valor_perdido,cantidad_perdida,motivo'];
    for (final log in logs) {
      final date = log['date'] ?? '';
      final value = (log['value_lost'] as num?)?.toStringAsFixed(2) ?? '0';
      final qty = log['quantity_lost']?.toString() ?? '0';
      final reason = (log['reason'] as String? ?? '').replaceAll(',', ';');
      lines.add('$date,$value,$qty,$reason');
    }
    final csv = lines.join('\n');
    try {
      final dir = await getTemporaryDirectory();
      final now = DateTime.now();
      final filename = 'merma_${now.year}${now.month.toString().padLeft(2, '0')}.csv';
      final file = File('${dir.path}/$filename');
      await file.writeAsString(csv);
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'text/csv')],
        subject: 'Registro merma MermaOps — ${logs.length} entradas',
      );
    } catch (_) {
      // Fallback: copy to clipboard
      Clipboard.setData(ClipboardData(text: csv));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('CSV copiado al portapapeles (${logs.length} registros)'),
            backgroundColor: const Color(0xFF059669),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_mermaHistoryProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
      data: (logs) {
        if (logs.isEmpty) {
          return const Center(child: Text('Sin registros de merma en los últimos 30 días'));
        }

        final totalValue = logs.fold<double>(
          0,
          (sum, l) => sum + ((l['value_lost'] as num?)?.toDouble() ?? 0),
        );
        final totalQty = logs.fold<int>(
          0,
          (sum, l) => sum + ((l['quantity_lost'] as int?) ?? 0),
        );

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Summary card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF059669), Color(0xFF10B981)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Merma últimos 30 días',
                              style: TextStyle(color: Colors.white70, fontSize: 12),
                            ),
                            Text(
                              '${totalValue.toStringAsFixed(2)} €',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 28,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          const Text(
                            'Unidades perdidas',
                            style: TextStyle(color: Colors.white70, fontSize: 12),
                          ),
                          Text(
                            '$totalQty uds',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerRight,
                    child: OutlinedButton.icon(
                      onPressed: () => _exportCsv(context, logs),
                      icon: const Icon(Icons.download, size: 16, color: Colors.white),
                      label: const Text(
                        'Exportar CSV',
                        style: TextStyle(color: Colors.white, fontSize: 12),
                      ),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.white54),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // Bar chart — last 14 days
            _MermaBarChart(logs: logs),
            const SizedBox(height: 20),
            const Text(
              'Historial de registros',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            ...logs.map((log) {
              final date = log['date'] as String? ?? '';
              final valueLost = (log['value_lost'] as num?)?.toDouble() ?? 0;
              final qtyLost = log['quantity_lost'] as int? ?? 0;
              final reason = log['reason'] as String? ?? '';
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            reason.isEmpty ? 'Sin descripción' : reason,
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                          ),
                          Text(
                            date,
                            style: const TextStyle(fontSize: 11, color: Colors.grey),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          '-${valueLost.toStringAsFixed(2)} €',
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFFEF4444),
                          ),
                        ),
                        Text(
                          '$qtyLost uds',
                          style: const TextStyle(fontSize: 11, color: Colors.grey),
                        ),
                      ],
                    ),
                  ],
                ),
              );
            }),
          ],
        );
      },
    );
  }
}

class _SuppliersTab extends ConsumerWidget {
  const _SuppliersTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_suppliersProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              const Text('Backend no disponible', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text('$e', style: const TextStyle(fontSize: 12, color: Colors.grey),
                  textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
      data: (suppliers) {
        if (suppliers.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.local_shipping_outlined, size: 48, color: Colors.grey),
                  SizedBox(height: 12),
                  Text('Sin datos de proveedores',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  SizedBox(height: 4),
                  Text('Ejecuta el seed con datos demo para ver esta pantalla.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey)),
                ],
              ),
            ),
          );
        }

        final maxMerma = suppliers.fold<double>(
          0, (m, s) => ((s['avg_merma_pct'] as num?)?.toDouble() ?? 0) > m
              ? (s['avg_merma_pct'] as num).toDouble()
              : m,
        );

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                const Text('Ficha de proveedores',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                const Spacer(),
                Text('${suppliers.length} proveedores',
                    style: const TextStyle(fontSize: 12, color: Colors.grey)),
              ],
            ),
            const SizedBox(height: 4),
            const Text(
              'Merma promedio por proveedor — base para negociación',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 16),
            ...suppliers.map((s) => _SupplierCard(supplier: s, maxMerma: maxMerma)),
          ],
        );
      },
    );
  }
}

class _SupplierCard extends StatelessWidget {
  final Map<String, dynamic> supplier;
  final double maxMerma;

  const _SupplierCard({required this.supplier, required this.maxMerma});

  @override
  Widget build(BuildContext context) {
    final name = supplier['name'] as String? ?? 'Proveedor';
    final contact = supplier['contact'] as String? ?? '';
    final avgMerma = (supplier['avg_merma_pct'] as num?)?.toDouble() ?? 0;
    final productCount = supplier['product_count'] as int? ?? 0;
    final risk = supplier['risk'] as String? ?? 'BAJO';

    final riskColor = risk == 'ALTO'
        ? UrgencyColors.critical
        : risk == 'MEDIO'
            ? UrgencyColors.medium
            : UrgencyColors.low;

    final barRatio = maxMerma > 0 ? avgMerma / maxMerma : 0.0;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: riskColor.withValues(alpha: 0.25)),
        boxShadow: [
          BoxShadow(
            color: riskColor.withValues(alpha: 0.06),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(name,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w700)),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: riskColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  risk,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: riskColor,
                  ),
                ),
              ),
            ],
          ),
          if (contact.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(contact,
                style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ],
          const SizedBox(height: 12),
          // Merma bar
          Row(
            children: [
              SizedBox(
                width: 80,
                child: Text(
                  '${avgMerma.toStringAsFixed(1)}% merma',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: riskColor,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: barRatio,
                    minHeight: 8,
                    backgroundColor: const Color(0xFFE5E7EB),
                    valueColor: AlwaysStoppedAnimation<Color>(riskColor),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '$productCount producto(s) suministrado(s)',
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
          if (risk == 'ALTO') ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFFFEE2E2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: const [
                  Icon(Icons.lightbulb_outline,
                      size: 14, color: Color(0xFF991B1B)),
                  SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Merma elevada — revisar condiciones de transporte y plazos de entrega con este proveedor.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF991B1B)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MermaBarChart extends StatelessWidget {
  final List<Map<String, dynamic>> logs;

  const _MermaBarChart({required this.logs});

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    // Last 14 days oldest→newest
    final days = List.generate(14, (i) => now.subtract(Duration(days: 13 - i)));

    final Map<String, double> byDate = {};
    for (final log in logs) {
      final date = log['date'] as String? ?? '';
      byDate[date] = (byDate[date] ?? 0) + ((log['value_lost'] as num?)?.toDouble() ?? 0);
    }

    final values = days.map((d) {
      return byDate[d.toIso8601String().substring(0, 10)] ?? 0.0;
    }).toList();

    final maxVal = values.fold<double>(0, (a, b) => b > a ? b : a);
    if (maxVal == 0) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE5E7EB)),
        ),
        child: const Row(
          children: [
            Icon(Icons.bar_chart, color: Colors.grey, size: 28),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Merma diaria (€)',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                  SizedBox(height: 2),
                  Text('Sin registros de merma en los últimos 14 días.',
                      style: TextStyle(fontSize: 12, color: Colors.grey)),
                  Text('Las acciones completadas generan entradas automáticamente.',
                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ),
            ),
          ],
        ),
      );
    }

    final todayKey = now.toIso8601String().substring(0, 10);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Merma diaria (€)',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              const Text(
                'últimos 14 días',
                style: TextStyle(fontSize: 11, color: Colors.grey),
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 88,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: List.generate(14, (i) {
                final ratio = values[i] / maxVal;
                final isToday = days[i].toIso8601String().substring(0, 10) == todayKey;
                final hasValue = values[i] > 0;
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Tooltip(
                      message:
                          '${days[i].day}/${days[i].month}: ${values[i].toStringAsFixed(2)} €',
                      child: AnimatedContainer(
                        duration: Duration(milliseconds: 300 + i * 30),
                        curve: Curves.easeOut,
                        height: hasValue ? (6 + ratio * 82) : 4,
                        decoration: BoxDecoration(
                          color: isToday
                              ? const Color(0xFF059669)
                              : hasValue
                                  ? const Color(0xFF6EE7B7)
                                  : const Color(0xFFF3F4F6),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: List.generate(14, (i) {
              final d = days[i];
              // Show label only at start, midpoint and today
              final show = i == 0 || i == 6 || i == 13;
              return Expanded(
                child: Text(
                  show ? '${d.day}/${d.month}' : '',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 9,
                    color: i == 13 ? const Color(0xFF059669) : Colors.grey,
                    fontWeight: i == 13 ? FontWeight.w700 : FontWeight.normal,
                  ),
                ),
              );
            }),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _LegendDot(color: const Color(0xFF059669), label: 'Hoy'),
              const SizedBox(width: 12),
              _LegendDot(color: const Color(0xFF6EE7B7), label: 'Días anteriores'),
              const SizedBox(width: 12),
              _LegendDot(color: const Color(0xFFF3F4F6), label: 'Sin merma'),
            ],
          ),
        ],
      ),
    );
  }
}

class _OrderSuggestionsTab extends ConsumerWidget {
  const _OrderSuggestionsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_orderSuggestionsProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              const Text('Backend no disponible',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text('$e',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                  textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
      data: (suggestions) {
        if (suggestions.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.shopping_cart_outlined, size: 48, color: Colors.grey),
                  SizedBox(height: 12),
                  Text('Sin sugerencias de pedido',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  SizedBox(height: 4),
                  Text(
                    'Se calculan cuando hay historial de merma de al menos 7 días.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        }

        final totalValue = suggestions.fold<double>(
          0, (s, e) => s + ((e['estimated_value'] as num?)?.toDouble() ?? 0));

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF2563EB), Color(0xFF3B82F6)],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  const Icon(Icons.shopping_cart, color: Colors.white, size: 32),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Sugerencia de pedido semanal',
                          style: TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                        Text(
                          '${suggestions.length} productos',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      const Text(
                        'Valor estimado',
                        style: TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                      Text(
                        '${totalValue.toStringAsFixed(2)} €',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFEFF6FF),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, size: 14, color: Color(0xFF2563EB)),
                  SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Basado en merma histórica. Ajusta según acuerdos con proveedores y temporada.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF1D4ED8)),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Productos a pedir esta semana',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            ...suggestions.map((s) => _OrderSuggestionRow(suggestion: s)),
          ],
        );
      },
    );
  }
}

class _OrderSuggestionRow extends StatelessWidget {
  final Map<String, dynamic> suggestion;
  const _OrderSuggestionRow({required this.suggestion});

  @override
  Widget build(BuildContext context) {
    final name = suggestion['product_name'] as String? ?? 'Producto';
    final category = suggestion['category'] as String? ?? '';
    final pasillo = suggestion['pasillo'] as String? ?? '?';
    final orderQty = suggestion['order_qty'] as int? ?? 0;
    final warehouseStock = suggestion['current_warehouse_stock'] as int? ?? 0;
    final avgDaily = (suggestion['avg_daily_loss'] as num?)?.toDouble() ?? 0;
    final estimatedValue = (suggestion['estimated_value'] as num?)?.toDouble() ?? 0;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Center(
              child: Text(
                '$orderQty',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF2563EB),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 13)),
                Text(
                  '$category · Pasillo $pasillo · almacén: $warehouseStock uds',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${estimatedValue.toStringAsFixed(2)} €',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF2563EB),
                ),
              ),
              Text(
                '${avgDaily.toStringAsFixed(1)} uds/día',
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ── ESG Tab ───────────────────────────────────────────────────────────────────

class _EsgTab extends StatefulWidget {
  const _EsgTab();

  @override
  State<_EsgTab> createState() => _EsgTabState();
}

class _EsgTabState extends State<_EsgTab> {
  late final Future<Map<String, dynamic>> _statsFuture;
  bool _loadingReport = false;
  String? _reportText;

  @override
  void initState() {
    super.initState();
    _statsFuture = api.getEsgStats(days: 30);
  }

  Future<void> _loadReport() async {
    setState(() => _loadingReport = true);
    try {
      final data = await api.getEsgReport(days: 30);
      setState(() => _reportText = data['report'] as String? ?? '');
    } catch (e) {
      setState(() => _reportText = 'Error generando informe: $e');
    } finally {
      setState(() => _loadingReport = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _statsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.eco_outlined, size: 48, color: Colors.grey),
                  const SizedBox(height: 12),
                  const Text('ESG no disponible',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('${snapshot.error}',
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                      textAlign: TextAlign.center),
                ],
              ),
            ),
          );
        }
        final esg = snapshot.data ?? {};
        final co2 = (esg['estimated_co2_avoided_kg'] as num?)?.toDouble() ?? 0;
        final water = (esg['estimated_water_avoided_liters'] as num?)?.toDouble() ?? 0;
        final valueRecovered = (esg['value_recovered_eur'] as num?)?.toDouble() ?? 0;
        final donated = (esg['donated_value_eur'] as num?)?.toDouble() ?? 0;
        final taxDeduction = (esg['tax_deduction_estimate_eur'] as num?)?.toDouble() ?? 0;
        final score = esg['esg_score'] as int? ?? 0;
        final eq = esg['equivalences'] as Map<String, dynamic>? ?? {};
        final kmCar = (eq['km_car_avoided'] as num?)?.toDouble() ?? 0;
        final showerDays = (eq['shower_days_equivalent'] as num?)?.toDouble() ?? 0;
        final actions = esg['actions_completed'] as int? ?? 0;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Score header
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF065F46), Color(0xFF059669)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  const Icon(Icons.eco, color: Colors.white, size: 40),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Puntuación ESG',
                            style: TextStyle(color: Colors.white70, fontSize: 12)),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text('$score',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 48,
                                    fontWeight: FontWeight.w900,
                                    height: 1)),
                            const Text('/100',
                                style: TextStyle(
                                    color: Colors.white60, fontSize: 18)),
                          ],
                        ),
                        const Text('últimos 30 días',
                            style: TextStyle(color: Colors.white60, fontSize: 11)),
                      ],
                    ),
                  ),
                  CircularProgressIndicator(
                    value: score / 100,
                    strokeWidth: 6,
                    backgroundColor: Colors.white24,
                    valueColor: AlwaysStoppedAnimation<Color>(
                        score >= 70 ? const Color(0xFF6EE7B7) : Colors.orangeAccent),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Métricas ambientales
            Row(
              children: [
                Expanded(
                  child: _EsgMetricCard(
                    icon: Icons.cloud_outlined,
                    color: const Color(0xFF3B82F6),
                    value: '${co2.toStringAsFixed(1)} kg',
                    label: 'CO₂ evitado',
                    sublabel: '≈ ${kmCar.toStringAsFixed(0)} km en coche',
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _EsgMetricCard(
                    icon: Icons.water_drop_outlined,
                    color: const Color(0xFF06B6D4),
                    value: '${(water / 1000).toStringAsFixed(1)} m³',
                    label: 'Agua ahorrada',
                    sublabel: '≈ ${showerDays.toStringAsFixed(0)} duchas',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _EsgMetricCard(
                    icon: Icons.euro_outlined,
                    color: const Color(0xFF8B5CF6),
                    value: '${valueRecovered.toStringAsFixed(2)} €',
                    label: 'Valor recuperado',
                    sublabel: '$actions acciones completadas',
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _EsgMetricCard(
                    icon: Icons.receipt_long_outlined,
                    color: const Color(0xFFD97706),
                    value: '${taxDeduction.toStringAsFixed(2)} €',
                    label: 'Deducción fiscal',
                    sublabel: 'Donado: ${donated.toStringAsFixed(2)} €',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Info fiscal
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFFFFBEB),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFFDE68A)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.lightbulb_outline,
                      size: 18, color: Color(0xFFD97706)),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Las donaciones alimentarias tienen deducción del 35% (Ley 49/2002). '
                      'El reporting ESG será obligatorio para PYMEs en 2025 (CSRD).',
                      style: TextStyle(
                          fontSize: 11, color: Color(0xFF92400E)),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Botón informe IA
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _loadingReport ? null : _loadReport,
                icon: _loadingReport
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.auto_awesome, size: 18),
                label: Text(_loadingReport
                    ? 'Generando informe ESG...'
                    : 'Generar informe ESG completo (IA)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF059669),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),

            if (_reportText != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFD1FAE5)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.eco, size: 16, color: Color(0xFF059669)),
                        SizedBox(width: 6),
                        Text('Informe ESG — Últimos 30 días',
                            style: TextStyle(
                                fontSize: 13, fontWeight: FontWeight.w700)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(_reportText!,
                        style: const TextStyle(fontSize: 13, height: 1.5)),
                  ],
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _EsgMetricCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String value;
  final String label;
  final String sublabel;

  const _EsgMetricCard({
    required this.icon,
    required this.color,
    required this.value,
    required this.label,
    required this.sublabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 8),
          Text(value,
              style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: color)),
          Text(label,
              style: const TextStyle(
                  fontSize: 11, fontWeight: FontWeight.w600)),
          Text(sublabel,
              style: const TextStyle(fontSize: 10, color: Colors.grey)),
        ],
      ),
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;

  const _LegendDot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(2),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 10, color: Colors.grey)),
      ],
    );
  }
}

// ── PDF Download Button ────────────────────────────────────────────────────────

class _PdfDownloadButton extends StatefulWidget {
  final String label;
  final Future<List<int>> Function() download;
  final String filename;

  const _PdfDownloadButton({
    required this.label,
    required this.download,
    required this.filename,
  });

  @override
  State<_PdfDownloadButton> createState() => _PdfDownloadButtonState();
}

class _PdfDownloadButtonState extends State<_PdfDownloadButton> {
  bool _loading = false;

  Future<void> _handleTap() async {
    setState(() => _loading = true);
    try {
      final bytes = await widget.download();
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/${widget.filename}');
      await file.writeAsBytes(bytes);
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: widget.label,
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error descargando PDF: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: _loading ? null : _handleTap,
      icon: _loading
          ? const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.picture_as_pdf_outlined, size: 16),
      label: Text(_loading ? 'Generando...' : widget.label,
          style: const TextStyle(fontSize: 12)),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF059669),
        side: const BorderSide(color: Color(0xFF059669)),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}

// ── Predictions Tab ───────────────────────────────────────────────────────────

class _PredictionsTab extends StatefulWidget {
  const _PredictionsTab();

  @override
  State<_PredictionsTab> createState() => _PredictionsTabState();
}

class _PredictionsTabState extends State<_PredictionsTab> {
  late final Future<Map<String, dynamic>> _riskFuture;
  bool _loadingBrief = false;
  String? _briefText;

  @override
  void initState() {
    super.initState();
    _riskFuture = _loadRisk();
  }

  Future<Map<String, dynamic>> _loadRisk() async {
    final predictions = await api.getRiskPredictions(days: 5);
    return predictions;
  }

  Future<void> _loadBrief() async {
    setState(() => _loadingBrief = true);
    try {
      final data = await api.getPredictionBrief(days: 5);
      setState(() => _briefText = data['brief'] as String? ?? '');
    } catch (e) {
      setState(() => _briefText = 'Error generando briefing: $e');
    } finally {
      setState(() => _loadingBrief = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _riskFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.auto_graph, size: 48, color: Colors.grey),
                  const SizedBox(height: 12),
                  const Text('Predicciones no disponibles',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('${snapshot.error}',
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                      textAlign: TextAlign.center),
                ],
              ),
            ),
          );
        }

        final data = snapshot.data ?? {};
        final predictions =
            List<Map<String, dynamic>>.from(data['predictions'] as List? ?? []);
        final forecastDays = data['forecast_days'] as int? ?? 5;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Header
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF312E81), Color(0xFF6D28D9)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  const Icon(Icons.auto_graph, color: Colors.white, size: 36),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Predicción de merma',
                            style: TextStyle(
                                color: Colors.white70, fontSize: 12)),
                        Text('Próximos $forecastDays días',
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.w800)),
                        const Text(
                            'Meteorología Open-Meteo · Patrones históricos',
                            style: TextStyle(
                                color: Colors.white60, fontSize: 10)),
                      ],
                    ),
                  ),
                  Column(
                    children: [
                      Text('${predictions.length}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 36,
                              fontWeight: FontWeight.w900,
                              height: 1)),
                      const Text('en riesgo',
                          style:
                              TextStyle(color: Colors.white60, fontSize: 10)),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Botón briefing IA
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _loadingBrief ? null : _loadBrief,
                icon: _loadingBrief
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.auto_awesome, size: 18),
                label: Text(_loadingBrief
                    ? 'Generando briefing predictivo...'
                    : 'Generar briefing predictivo (IA + meteorología)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF6D28D9),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),

            if (_briefText != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF5F3FF),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFDDD6FE)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.auto_graph,
                            size: 14, color: Color(0xFF6D28D9)),
                        SizedBox(width: 6),
                        Text('Briefing predictivo',
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF6D28D9))),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(_briefText!,
                        style:
                            const TextStyle(fontSize: 13, height: 1.5)),
                  ],
                ),
              ),
            ],

            const SizedBox(height: 16),

            if (predictions.isEmpty)
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: const Color(0xFFF0FDF4),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFBBF7D0)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.check_circle_outline,
                        color: Color(0xFF059669), size: 32),
                    SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Sin riesgos detectados',
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF065F46))),
                          Text(
                              'Ningún producto en riesgo predictivo para los próximos días.',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: Color(0xFF047857))),
                        ],
                      ),
                    ),
                  ],
                ),
              )
            else ...[
              Text('Productos en riesgo (ordenados por score):',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: Colors.grey[700])),
              const SizedBox(height: 8),
              ...predictions.map((p) => _PredictionCard(prediction: p)),
            ],
          ],
        );
      },
    );
  }
}

class _PredictionCard extends StatelessWidget {
  final Map<String, dynamic> prediction;

  const _PredictionCard({required this.prediction});

  @override
  Widget build(BuildContext context) {
    final score = prediction['risk_score'] as int? ?? 0;
    final name = prediction['product_name'] as String? ?? '?';
    final daysLeft = prediction['days_until_expiry'] as int? ?? 0;
    final qty = prediction['quantity'] as int? ?? 0;
    final value = (prediction['value_at_risk'] as num?)?.toDouble() ?? 0;
    final factors =
        List<String>.from(prediction['risk_factors'] as List? ?? []);
    final action =
        prediction['recommended_preemptive_action'] as String? ?? '';
    final weatherAlert = prediction['weather_alert'] as bool? ?? false;
    final pasillo = prediction['pasillo'] as String? ?? '?';

    final scoreColor = score >= 70
        ? const Color(0xFFDC2626)
        : score >= 50
            ? const Color(0xFFD97706)
            : const Color(0xFF3B82F6);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scoreColor.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: scoreColor,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text('$score',
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 13)),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(name,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 14)),
              ),
              if (weatherAlert)
                const Icon(Icons.wb_sunny_outlined,
                    size: 16, color: Color(0xFFD97706)),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              _PredChip(
                  icon: Icons.schedule,
                  label: 'Caduca en ${daysLeft}d',
                  color: daysLeft <= 5
                      ? const Color(0xFFD97706)
                      : Colors.grey),
              const SizedBox(width: 6),
              _PredChip(
                  icon: Icons.inventory_2_outlined,
                  label: '$qty uds · ${value.toStringAsFixed(0)}€',
                  color: Colors.grey),
              const SizedBox(width: 6),
              _PredChip(
                  icon: Icons.store_mall_directory_outlined,
                  label: 'Pasillo $pasillo',
                  color: Colors.grey),
            ],
          ),
          if (factors.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(factors.first,
                style: const TextStyle(
                    fontSize: 11, color: Color(0xFF6B7280))),
          ],
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding:
                const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFFF3F4F6),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(action,
                style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF374151))),
          ),
        ],
      ),
    );
  }
}

class _PredChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _PredChip(
      {required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 11, color: color),
        const SizedBox(width: 2),
        Text(label,
            style: TextStyle(
                fontSize: 10,
                color: color,
                fontWeight: FontWeight.w600)),
      ],
    );
  }
}

// ── Analizar PDF Tab ──────────────────────────────────────────────────────────

class _AnalyzePdfTab extends StatefulWidget {
  const _AnalyzePdfTab();

  @override
  State<_AnalyzePdfTab> createState() => _AnalyzePdfTabState();
}

class _AnalyzePdfTabState extends State<_AnalyzePdfTab> {
  bool _loading = false;
  String? _fileName;
  String? _analysis;
  String? _error;
  int? _pages;

  Future<void> _pickAndAnalyze() async {
    setState(() {
      _loading = true;
      _error = null;
      _analysis = null;
      _fileName = null;
      _pages = null;
    });

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf'],
        withData: true,
      );

      if (result == null || result.files.isEmpty) {
        setState(() => _loading = false);
        return;
      }

      final file = result.files.single;
      final bytes = file.bytes;
      if (bytes == null) {
        setState(() {
          _error = 'No se pudieron leer los bytes del archivo.';
          _loading = false;
        });
        return;
      }

      setState(() => _fileName = file.name);

      final data = await api.analyzePdfReport(bytes, file.name);
      setState(() {
        _analysis = data['analysis'] as String? ?? '';
        _pages = data['pages'] as int?;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Error analizando PDF: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Header card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF1E1B4B), Color(0xFF4C1D95)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(children: [
                Icon(Icons.auto_awesome, color: Colors.white, size: 22),
                SizedBox(width: 10),
                Text('Analizar PDF con IA',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w800)),
              ]),
              const SizedBox(height: 8),
              const Text(
                'Importa cualquier informe del supervisor, brief mensual o '
                'documento de merma. Claude lo analiza y extrae KPIs, '
                'problemas y recomendaciones concretas.',
                style: TextStyle(color: Colors.white70, fontSize: 13, height: 1.5),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _loading ? null : _pickAndAnalyze,
                  icon: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Color(0xFF4C1D95)))
                      : const Icon(Icons.upload_file_rounded, size: 20),
                  label: Text(_loading
                      ? 'Analizando con Claude...'
                      : 'Seleccionar PDF e importar'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: const Color(0xFF4C1D95),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                    textStyle: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 15),
                  ),
                ),
              ),
            ],
          ),
        ),

        // File info pill
        if (_fileName != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFF5F3FF),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFDDD6FE)),
            ),
            child: Row(children: [
              const Icon(Icons.picture_as_pdf_rounded,
                  color: Color(0xFF7C3AED), size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_fileName!,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                            color: Color(0xFF4C1D95))),
                    if (_pages != null)
                      Text('$_pages páginas extraídas',
                          style: const TextStyle(
                              fontSize: 11, color: Color(0xFF7C3AED))),
                  ],
                ),
              ),
              if (_loading)
                const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Color(0xFF7C3AED))),
            ]),
          ),
        ],

        // Error
        if (_error != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFEF2F2),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFFECACA)),
            ),
            child: Row(children: [
              const Icon(Icons.error_outline_rounded,
                  size: 16, color: Color(0xFFEF4444)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(_error!,
                    style: const TextStyle(
                        fontSize: 12, color: Color(0xFFDC2626))),
              ),
            ]),
          ),
        ],

        // Analysis result
        if (_analysis != null && _analysis!.isNotEmpty) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE0E7FF)),
              boxShadow: [
                BoxShadow(
                    color: const Color(0xFF6D28D9).withValues(alpha: 0.07),
                    blurRadius: 12,
                    offset: const Offset(0, 4)),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(children: [
                  Icon(Icons.auto_awesome,
                      size: 16, color: Color(0xFF7C3AED)),
                  SizedBox(width: 6),
                  Text('Análisis de Claude',
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF4C1D95))),
                ]),
                const SizedBox(height: 12),
                SelectableText(
                  _analysis!,
                  style: const TextStyle(
                      fontSize: 13, height: 1.65, color: Color(0xFF374151)),
                ),
                const SizedBox(height: 14),
                OutlinedButton.icon(
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: _analysis!));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                          content: Text('Análisis copiado al portapapeles'),
                          backgroundColor: Color(0xFF059669)),
                    );
                  },
                  icon: const Icon(Icons.copy_rounded, size: 14),
                  label: const Text('Copiar análisis'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF7C3AED),
                    side: const BorderSide(color: Color(0xFF7C3AED)),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    textStyle: const TextStyle(fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ],

        // Empty state
        if (_analysis == null && !_loading && _error == null) ...[
          const SizedBox(height: 32),
          Center(
            child: Column(
              children: [
                Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF5F3FF),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(Icons.description_outlined,
                      size: 36, color: Color(0xFF7C3AED)),
                ),
                const SizedBox(height: 14),
                const Text('Importa un PDF para analizarlo',
                    style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: Color(0xFF374151))),
                const SizedBox(height: 6),
                const Text(
                  'Informes mensuales, briefs del supervisor,\ndocumentos de merma o cualquier PDF relevante.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 13),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}
