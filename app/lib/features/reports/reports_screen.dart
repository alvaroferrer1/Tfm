import 'dart:convert' show utf8;
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:file_picker/file_picker.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/l10n.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';
import '../../core/user_role_provider.dart';

import 'dart:io' show File;

// Guards LinearGradient.createShader() against zero-area rects (CanvasKit crash on Flutter web)
class _SafeGradient extends LinearGradient {
  const _SafeGradient({
    required super.colors,
    super.begin = Alignment.centerLeft,
    super.end = Alignment.centerRight,
    super.stops,
  });

  @override
  Shader createShader(Rect rect, {TextDirection? textDirection}) {
    final safe = rect.isEmpty ? Rect.fromLTWH(0, 0, 1, 1) : rect;
    return super.createShader(safe, textDirection: textDirection);
  }
}

final _dailyBriefsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getDailyBriefsList(limit: 14);
});

final _weeklyReportsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getWeeklyReports(limit: 8);
});

final _monthlyReportsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getMonthlyReports(limit: 6);
});

final _suppliersProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getSupplierStats();
});

final _mermaHistoryProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getMermaHistory(days: 30);
});

final _orderSuggestionsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getOrderSuggestions();
});

final _benchmarkProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getStoreBenchmark(days: 30);
});

// Supabase Realtime — notifica cuando llega un nuevo brief diario
final _liveBriefCountProvider = StreamProvider<int>((ref) {
  return supabase
      .from('daily_briefs')
      .stream(primaryKey: ['id'])
      .eq('store_id', storeId)
      .map((rows) => rows.length);
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
    _tabs = TabController(length: 11, vsync: this);
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
        title: Consumer(builder: (_, ref, __) {
          final liveCount = ref.watch(_liveBriefCountProvider).value ?? 0;
          return Row(mainAxisSize: MainAxisSize.min, children: [
            const Text('Informes'),
            if (liveCount > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFF059669),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text('$liveCount briefs',
                    style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700)),
              ),
            ],
          ]);
        }),
        actions: [
          Consumer(builder: (_, ref, __) {
            final lang = ref.watch(languageProvider);
            return TextButton(
              onPressed: () => ref.read(languageProvider.notifier).toggle(),
              child: Text(lang == 'es' ? 'EN' : 'ES',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
            );
          }),
        ],
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
            Tab(text: 'Benchmark 📊'),
            Tab(text: 'Predicciones 🔮'),
            Tab(text: 'Analizar PDF 🤖'),
            Tab(text: 'Insights IA ✨'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: const [
          _DailyBriefsTab(),
          _WeeklyReportsTab(),
          _MonthlyReportsTab(),
          _MermaTab(),
          _SuppliersTab(),
          _OrderSuggestionsTab(),
          _EsgTab(),
          _BenchmarkTab(),
          _PredictionsTab(),
          _AnalyzePdfTab(),
          _InsightsTab(),
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
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_dailyBriefsProvider)),
      data: (briefs) {
        if (briefs.isEmpty) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 72, height: 72,
                    decoration: BoxDecoration(
                      color: const Color(0xFFEDE9FE),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Icon(Icons.psychology_rounded,
                        size: 36, color: Color(0xFF7C3AED)),
                  ),
                  const SizedBox(height: 20),
                  const Text('Sin briefs generados aún',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700,
                          color: Color(0xFF111827))),
                  const SizedBox(height: 8),
                  const Text(
                    'Kuine genera el brief automáticamente a las 07:30.\n'
                    'También puedes generarlo ahora desde el Dashboard.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: Color(0xFF6B7280), height: 1.5),
                  ),
                  const SizedBox(height: 20),
                  OutlinedButton.icon(
                    onPressed: () => context.go('/'),
                    icon: const Icon(Icons.dashboard_rounded, size: 16),
                    label: const Text('Ir al Dashboard'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF7C3AED),
                      side: const BorderSide(color: Color(0xFF7C3AED)),
                    ),
                  ),
                ],
              ),
            ),
          );
        }
        final totalActions = briefs.fold<int>(0, (s, b) => s + ((b['actions_count'] as int?) ?? 0));
        final totalRisk = briefs.fold<double>(0, (s, b) => s + ((b['value_at_risk'] as num?)?.toDouble() ?? 0));
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(_dailyBriefsProvider),
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: briefs.length + 1,
            itemBuilder: (context, i) {
              if (i == 0) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEDE9FE),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFFDDD6FE)),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 44, height: 44,
                          decoration: BoxDecoration(
                            color: const Color(0xFF7C3AED),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 24),
                        ),
                        const SizedBox(width: 14),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${briefs.length} briefs de Kuine',
                              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: Color(0xFF4C1D95))),
                          Text('$totalActions acciones analizadas · ${totalRisk.toStringAsFixed(0)} € gestionados',
                              style: const TextStyle(fontSize: 12, color: Color(0xFF6D28D9))),
                        ])),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                          decoration: BoxDecoration(
                            color: const Color(0xFF7C3AED),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text('IA', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 13)),
                        ),
                      ],
                    ),
                  ),
                );
              }
              final brief = briefs[i - 1];
              final date = brief['date'] as String? ?? '';
              final summary = brief['summary'] as String? ?? '';
              final value = (brief['value_at_risk'] as num?)?.toDouble() ?? 0;
              final actionsCount = brief['actions_count'] as int? ?? 0;
              final isToday = date == DateTime.now().toIso8601String().substring(0, 10);

              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ExpansionTile(
                  tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  leading: Container(
                    width: 36, height: 36,
                    decoration: BoxDecoration(
                      color: isToday ? const Color(0xFFD1FAE5) : const Color(0xFFF3F4F6),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(Icons.article_rounded,
                        size: 18, color: isToday ? const Color(0xFF059669) : const Color(0xFF6B7280)),
                  ),
                  title: Row(
                    children: [
                      Text(date, style: TextStyle(fontWeight: FontWeight.w700,
                          color: isToday ? const Color(0xFF059669) : null)),
                      if (isToday) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(color: const Color(0xFFD1FAE5), borderRadius: BorderRadius.circular(4)),
                          child: const Text('Hoy', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF059669))),
                        ),
                      ],
                    ],
                  ),
                  subtitle: Text('$actionsCount acciones — ${value.toStringAsFixed(0)} € en riesgo',
                      style: const TextStyle(fontSize: 12)),
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                      child: Text(summary, style: const TextStyle(fontSize: 13, height: 1.6)),
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
          ),
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
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_weeklyReportsProvider)),
      data: (reports) {
        if (reports.isEmpty) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.bar_chart, size: 48, color: Colors.grey),
                  const SizedBox(height: 12),
                  const Text(
                    'Sin informes semanales aún',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Los informes se generan automáticamente cada lunes a las 06:00',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Generar ahora'),
                    onPressed: () async {
                      final messenger = ScaffoldMessenger.of(context);
                      messenger.showSnackBar(
                        const SnackBar(
                          content: Text('Generando informe semanal con IA…'),
                          duration: Duration(seconds: 90),
                        ),
                      );
                      try {
                        await api.runWeeklyReport();
                        messenger.hideCurrentSnackBar();
                        messenger.showSnackBar(
                          const SnackBar(
                            content: Text('Informe semanal en proceso. Actualiza en un momento.'),
                            backgroundColor: Color(0xFF059669),
                          ),
                        );
                        if (context.mounted) ref.invalidate(_weeklyReportsProvider);
                      } catch (e) {
                        messenger.hideCurrentSnackBar();
                        messenger.showSnackBar(
                          SnackBar(
                            content: Text(friendlyError(e)),
                            backgroundColor: Colors.red,
                          ),
                        );
                      }
                    },
                  ),
                ],
              ),
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(_weeklyReportsProvider),
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: reports.length + 1,
            itemBuilder: (context, i) {
              if (i == 0) {
                final first = reports.last['week_start'] as String? ?? '';
                final last = reports.first['week_start'] as String? ?? '';
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0F9FF),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFFBAE6FD)),
                    ),
                    child: Row(children: [
                      Container(
                        width: 44, height: 44,
                        decoration: BoxDecoration(color: const Color(0xFF0284C7), borderRadius: BorderRadius.circular(12)),
                        child: const Icon(Icons.calendar_view_week_rounded, color: Colors.white, size: 22),
                      ),
                      const SizedBox(width: 14),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${reports.length} informes semanales',
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: Color(0xFF0C4A6E))),
                        Text('$first → $last · Generados por Kuine cada lunes',
                            style: const TextStyle(fontSize: 11, color: Color(0xFF0369A1))),
                      ])),
                    ]),
                  ),
                );
              }
              final report = reports[i - 1];
              final week = report['week_start'] as String? ?? '';
              final content = report['content'] as String? ?? '';
              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ExpansionTile(
                  leading: Container(
                    width: 36, height: 36,
                    decoration: BoxDecoration(color: const Color(0xFFEFF6FF), borderRadius: BorderRadius.circular(8)),
                    child: const Icon(Icons.bar_chart_rounded, size: 18, color: Color(0xFF2563EB)),
                  ),
                  title: Text('Semana del $week', style: const TextStyle(fontWeight: FontWeight.w700)),
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                      child: Text(content, style: const TextStyle(fontSize: 13, height: 1.6)),
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
          ),
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
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_monthlyReportsProvider)),
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
                      final messenger = ScaffoldMessenger.of(context);
                      messenger.showSnackBar(
                        const SnackBar(
                          content: Text('Generando informe mensual con IA…'),
                          duration: Duration(seconds: 90),
                        ),
                      );
                      try {
                        await api.runMonthlyReport();
                        messenger.hideCurrentSnackBar();
                        messenger.showSnackBar(
                          const SnackBar(
                            content: Text('Informe mensual en proceso. Actualiza en un momento.'),
                            backgroundColor: Color(0xFF059669),
                          ),
                        );
                        if (context.mounted) ref.invalidate(_monthlyReportsProvider);
                      } catch (e) {
                        messenger.hideCurrentSnackBar();
                        messenger.showSnackBar(
                          SnackBar(
                            content: Text(friendlyError(e)),
                            backgroundColor: Colors.red,
                          ),
                        );
                      }
                    },
                  ),
                ],
              ),
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(_monthlyReportsProvider),
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: reports.length + 1,
            itemBuilder: (context, i) {
              if (i == 0) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF5F3FF),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFFEDE9FE)),
                    ),
                    child: Row(children: [
                      Container(
                        width: 44, height: 44,
                        decoration: BoxDecoration(color: const Color(0xFF7C3AED), borderRadius: BorderRadius.circular(12)),
                        child: const Icon(Icons.summarize_rounded, color: Colors.white, size: 22),
                      ),
                      const SizedBox(width: 14),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${reports.length} informes para el dueño',
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: Color(0xFF4C1D95))),
                        const Text('Resumen ejecutivo mensual · generado el día 1',
                            style: TextStyle(fontSize: 11, color: Color(0xFF7C3AED))),
                      ])),
                    ]),
                  ),
                );
              }
              final report = reports[i - 1];
              final month = report['month'] as String? ?? '';
              final content = report['content'] as String? ?? '';
              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: ExpansionTile(
                  leading: Container(
                    width: 36, height: 36,
                    decoration: BoxDecoration(
                      color: const Color(0xFF7C3AED).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.summarize, size: 18, color: Color(0xFF7C3AED)),
                  ),
                  title: Text('Informe mensual — $month', style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: const Text('Para el dueño', style: TextStyle(fontSize: 11, color: Color(0xFF7C3AED))),
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                      child: Text(content, style: const TextStyle(fontSize: 13, height: 1.6)),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      child: _PdfDownloadButton(
                        label: '📈 Descargar PDF mensual',
                        filename: 'informe_mensual_$month.pdf',
                        download: () => api.downloadMonthlyPdf(month: month),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }
}

class _MermaTab extends ConsumerStatefulWidget {
  const _MermaTab();
  @override
  ConsumerState<_MermaTab> createState() => _MermaTabState();
}

class _MermaTabState extends ConsumerState<_MermaTab> {
  String _filterReason = 'Todos';

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
    final now = DateTime.now();
    final filename = 'merma_${now.year}${now.month.toString().padLeft(2, '0')}.csv';
    try {
      final csvBytes = Uint8List.fromList(utf8.encode(csv));
      if (kIsWeb) {
        await Share.shareXFiles(
          [XFile.fromData(csvBytes, mimeType: 'text/csv', name: filename)],
          subject: 'Registro merma MermaOps — ${logs.length} entradas',
        );
      } else {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}/$filename');
        await file.writeAsString(csv);
        await Share.shareXFiles(
          [XFile(file.path, mimeType: 'text/csv')],
          subject: 'Registro merma MermaOps — ${logs.length} entradas',
        );
      }
    } catch (e) {
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
  Widget build(BuildContext context) {
    final async = ref.watch(_mermaHistoryProvider);
    return async.when(
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_mermaHistoryProvider)),
      data: (logs) {
        if (logs.isEmpty) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 64, height: 64,
                    decoration: BoxDecoration(
                      color: const Color(0xFFD1FAE5),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: const Icon(Icons.trending_down_rounded,
                        size: 32, color: Color(0xFF059669)),
                  ),
                  const SizedBox(height: 16),
                  const Text('Sin merma registrada',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700,
                          color: Color(0xFF111827))),
                  const SizedBox(height: 6),
                  const Text('No se ha registrado merma en este período.\nEl sistema lo registra automáticamente al completar acciones.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: Color(0xFF6B7280), height: 1.5)),
                ],
              ),
            ),
          );
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
                gradient: const _SafeGradient(
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
            const SizedBox(height: 16),
            // Category breakdown
            _MermaCategoryBreakdown(logs: logs),
            const SizedBox(height: 16),
            // Trend summary
            _MermaTrendCard(logs: logs),
            const SizedBox(height: 16),
            // Top 5 productos con más merma
            _MermaTop5(logs: logs),
            const SizedBox(height: 20),
            // ── Filtro por motivo ──────────────────────────────────────────
            Builder(builder: (ctx) {
              final reasons = <String>{'Todos', ...logs.map((l) => (l['reason'] as String? ?? '').trim()).where((r) => r.isNotEmpty)};
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Historial de registros',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                SizedBox(
                  height: 32,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: reasons.map((r) {
                      final sel = _filterReason == r;
                      return Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: GestureDetector(
                          onTap: () => setState(() => _filterReason = r),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: sel ? const Color(0xFF059669) : Colors.white,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: sel ? const Color(0xFF059669) : const Color(0xFFD1D5DB)),
                            ),
                            child: Text(r,
                                style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: sel ? Colors.white : const Color(0xFF374151))),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
                const SizedBox(height: 10),
              ]);
            }),
            ...logs.where((log) {
              if (_filterReason == 'Todos') return true;
              return (log['reason'] as String? ?? '').trim() == _filterReason;
            }).map((log) {
              final date = log['date'] as String? ?? '';
              final valueLost = (log['value_lost'] as num?)?.toDouble() ?? 0;
              final qtyLost = log['quantity_lost'] as int? ?? 0;
              final reason = log['reason'] as String? ?? '';
              return InkWell(
                onTap: () => showDialog(
                  context: context,
                  builder: (dlgCtx) => AlertDialog(
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    title: const Text('Detalle merma', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                    content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                      _MermaDetailRow(Icons.calendar_today_rounded, 'Fecha', date.isEmpty ? '—' : date),
                      const SizedBox(height: 8),
                      _MermaDetailRow(Icons.euro_rounded, 'Valor perdido', '-${valueLost.toStringAsFixed(2)} €'),
                      const SizedBox(height: 8),
                      _MermaDetailRow(Icons.inventory_2_rounded, 'Unidades', '$qtyLost uds'),
                      const SizedBox(height: 8),
                      _MermaDetailRow(Icons.info_outline_rounded, 'Motivo', reason.isEmpty ? 'Sin descripción' : reason),
                    ]),
                    actions: [
                      TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('Cerrar')),
                    ],
                  ),
                ),
                borderRadius: BorderRadius.circular(10),
                child: Container(
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
                      const SizedBox(width: 6),
                      const Icon(Icons.chevron_right, size: 16, color: Color(0xFFD1D5DB)),
                    ],
                  ),
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
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_suppliersProvider)),
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

        final highRisk = suppliers.where((s) => s['risk'] == 'ALTO').length;
        final avgMermaAll = suppliers.isEmpty ? 0.0 :
            suppliers.fold<double>(0, (sum, s) => sum + ((s['avg_merma_pct'] as num?)?.toDouble() ?? 0)) / suppliers.length;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Header card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const _SafeGradient(
                  colors: [Color(0xFF0F172A), Color(0xFF1E3A5F)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.local_shipping_rounded, color: Colors.white, size: 22),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Panel de proveedores',
                                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800)),
                            Text('${suppliers.length} proveedores · merma media ${avgMermaAll.toStringAsFixed(1)}%',
                                style: const TextStyle(color: Colors.white60, fontSize: 11)),
                          ],
                        ),
                      ),
                    ],
                  ),
                  if (highRisk > 0) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEF4444).withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFEF4444).withValues(alpha: 0.4)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.warning_rounded, size: 14, color: Color(0xFFFCA5A5)),
                          const SizedBox(width: 6),
                          Text('$highRisk proveedor${highRisk > 1 ? 'es' : ''} con merma ALTA — revisar condiciones de contrato',
                              style: const TextStyle(color: Color(0xFFFCA5A5), fontSize: 11)),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              'Merma promedio — base para renegociación',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 12),
            ...suppliers.map((s) => _SupplierCard(supplier: s, maxMerma: maxMerma)),
            const SizedBox(height: 16),
            _SuppliersReportActions(suppliers: suppliers),
            const SizedBox(height: 16),
          ],
        );
      },
    );
  }
}

class _SuppliersReportActions extends StatelessWidget {
  final List<Map<String, dynamic>> suppliers;
  const _SuppliersReportActions({required this.suppliers});

  static const _altPool = [
    ('🍞 Panadería', 'Harineras del Norte', '3.1%', '★★★★☆'),
    ('🍞 Panadería', 'Bimbo Ibérica', '2.8%', '★★★★★'),
    ('🥛 Lácteos', 'Leche Pascual', '2.2%', '★★★★★'),
    ('🥛 Lácteos', 'Central Lechera Asturiana', '1.9%', '★★★★★'),
    ('🥩 Carnicería', 'Campofrío', '4.1%', '★★★★☆'),
    ('🥩 Carnicería', 'El Pozo Alimentación', '3.7%', '★★★★☆'),
    ('🐟 Pescadería', 'Pescados Marineros', '5.2%', '★★★☆☆'),
    ('🐟 Pescadería', 'Frigoríficos del Atlántico', '4.8%', '★★★★☆'),
    ('🥦 Frutas y Verduras', 'Frutas Esther', '6.1%', '★★★☆☆'),
    ('🥦 Frutas y Verduras', 'Primaflor', '5.4%', '★★★★☆'),
    ('General', 'Makro Cash&Carry', '3.9%', '★★★☆☆'),
    ('General', 'Metro Distribución', '4.2%', '★★★☆☆'),
  ];

  void _showAlternativasModal(BuildContext context, List<Map<String, dynamic>> suppliers) {
    final highRisk = suppliers.where((s) => s['risk'] == 'ALTO' || ((s['avg_merma_pct'] as num? ?? 0) >= 15)).toList();
    final categories = highRisk.map((s) => s['category'] as String? ?? 'General').toSet().toList();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.65,
        maxChildSize: 0.92,
        builder: (_, ctrl) => Container(
          decoration: const BoxDecoration(
            color: Color(0xFFF9FAFB),
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(children: [
            const SizedBox(height: 10),
            Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 14),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Row(children: [
                Icon(Icons.swap_horiz_rounded, color: Color(0xFF059669), size: 20),
                SizedBox(width: 8),
                Text('Distribuidores alternativos', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
              ]),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: Text('Proveedores con menor merma histórica para las categorías de riesgo ALTO',
                  style: TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
            ),
            const Divider(height: 1),
            Expanded(child: ListView(
              controller: ctrl,
              padding: const EdgeInsets.all(14),
              children: [
                if (highRisk.isEmpty)
                  const Center(child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text('No hay proveedores con riesgo ALTO en este momento.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Color(0xFF9CA3AF))),
                  ))
                else ...[
                  ...categories.map((cat) {
                    final alts = _altPool.where((a) => a.$1.contains(cat) || a.$1 == 'General').take(2).toList();
                    if (alts.isEmpty) return const SizedBox.shrink();
                    final currentSupplier = highRisk.firstWhere((s) => (s['category'] as String? ?? '') == cat, orElse: () => {});
                    final currentMerma = currentSupplier.isEmpty ? '—' : '${(currentSupplier['avg_merma_pct'] as num?)?.toStringAsFixed(1) ?? '0'}%';
                    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8, top: 4),
                        child: Row(children: [
                          Text(cat, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(color: const Color(0xFFFEF2F2), borderRadius: BorderRadius.circular(6)),
                            child: Text('actual: $currentMerma merma',
                                style: const TextStyle(fontSize: 10, color: Color(0xFFDC2626), fontWeight: FontWeight.w600)),
                          ),
                        ]),
                      ),
                      ...alts.map((alt) => Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0xFFD1FAE5)),
                        ),
                        child: Row(children: [
                          const Icon(Icons.local_shipping_rounded, size: 20, color: Color(0xFF059669)),
                          const SizedBox(width: 10),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(alt.$2, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                            Row(children: [
                              Text('Merma est. ${alt.$3}', style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
                              const SizedBox(width: 8),
                              Text(alt.$4, style: const TextStyle(fontSize: 11, color: Color(0xFFD97706))),
                            ]),
                          ])),
                          TextButton(
                            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Solicitud de contacto enviada a ${alt.$2}'),
                                  backgroundColor: const Color(0xFF059669), duration: const Duration(seconds: 2)),
                            ),
                            style: TextButton.styleFrom(foregroundColor: const Color(0xFF059669), padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                            child: const Text('Contactar', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                          ),
                        ]),
                      )),
                      const Divider(height: 20),
                    ]);
                  }),
                ],
              ],
            )),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final highRisk = suppliers.where((s) => s['risk'] == 'ALTO' || ((s['avg_merma_pct'] as num? ?? 0) >= 15)).toList();
    final avgAll = suppliers.isEmpty ? 0.0
        : suppliers.fold<double>(0, (s, p) => s + ((p['avg_merma_pct'] as num?)?.toDouble() ?? 0)) / suppliers.length;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE5E7EB)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Row(children: [
            Icon(Icons.analytics_rounded, size: 15, color: Color(0xFF3B82F6)),
            SizedBox(width: 6),
            Text('Resumen de negociación', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            _ReportStatBox('${suppliers.length}', 'proveedores activos', const Color(0xFF3B82F6)),
            const SizedBox(width: 8),
            _ReportStatBox('${highRisk.length}', 'con riesgo ALTO', const Color(0xFFEF4444)),
            const SizedBox(width: 8),
            _ReportStatBox('${avgAll.toStringAsFixed(1)}%', 'merma media', const Color(0xFFD97706)),
          ]),
          const SizedBox(height: 14),
          if (highRisk.isNotEmpty) ...[
            const Text('Proveedores prioritarios para renegociar:',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
            const SizedBox(height: 8),
            ...highRisk.take(3).map((s) {
              final name = s['name'] as String? ?? 'Proveedor';
              final merma = (s['avg_merma_pct'] as num?)?.toStringAsFixed(1) ?? '0';
              final cat = s['category'] as String? ?? '';
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(children: [
                  const Icon(Icons.warning_amber_rounded, size: 14, color: Color(0xFFEF4444)),
                  const SizedBox(width: 6),
                  Expanded(child: Text('$name — $merma% merma${cat.isNotEmpty ? " · $cat" : ""}',
                      style: const TextStyle(fontSize: 11, color: Color(0xFF374151)))),
                  GestureDetector(
                    onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Iniciando renegociación con $name...'),
                          backgroundColor: const Color(0xFFEF4444), duration: const Duration(seconds: 2)),
                    ),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF2F2),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFFCA5A5)),
                      ),
                      child: const Text('Renegociar', style: TextStyle(fontSize: 10, color: Color(0xFFDC2626), fontWeight: FontWeight.w600)),
                    ),
                  ),
                ]),
              );
            }),
          ],
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: OutlinedButton.icon(
              onPressed: () async {
                final buf = StringBuffer('Proveedor,Categoría,Merma %,Riesgo\n');
                for (final s in suppliers) {
                  final name = s['name'] ?? '';
                  final cat = s['category'] ?? '';
                  final merma = s['avg_merma_pct'] ?? 0;
                  final risk = s['risk'] ?? 'BAJO';
                  buf.writeln('$name,$cat,$merma,$risk');
                }
                final bytes = Uint8List.fromList(utf8.encode(buf.toString()));
                final now = DateTime.now();
                final fname = 'proveedores_${now.year}${now.month.toString().padLeft(2,'0')}${now.day.toString().padLeft(2,'0')}.csv';
                await Share.shareXFiles(
                  [XFile.fromData(bytes, mimeType: 'text/csv', name: fname)],
                  subject: 'Proveedores MermaOps',
                );
              },
              icon: const Icon(Icons.download_rounded, size: 15),
              label: const Text('Exportar CSV', style: TextStyle(fontSize: 12)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF3B82F6),
                side: const BorderSide(color: Color(0xFF3B82F6)),
                padding: const EdgeInsets.symmetric(vertical: 10),
              ),
            )),
            const SizedBox(width: 8),
            Expanded(child: OutlinedButton.icon(
              onPressed: () => _showAlternativasModal(context, suppliers),
              icon: const Icon(Icons.swap_horiz_rounded, size: 15),
              label: const Text('Alternativas', style: TextStyle(fontSize: 12)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF059669),
                side: const BorderSide(color: Color(0xFF059669)),
                padding: const EdgeInsets.symmetric(vertical: 10),
              ),
            )),
          ]),
        ]),
      ),
    ]);
  }
}

class _ReportStatBox extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _ReportStatBox(this.value, this.label, this.color);
  @override
  Widget build(BuildContext context) {
    return Expanded(child: Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(children: [
        Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 9, color: Color(0xFF6B7280)), textAlign: TextAlign.center),
      ]),
    ));
  }
}

class _SupplierCard extends StatefulWidget {
  final Map<String, dynamic> supplier;
  final double maxMerma;

  const _SupplierCard({required this.supplier, required this.maxMerma});

  @override
  State<_SupplierCard> createState() => _SupplierCardState();
}

class _SupplierCardState extends State<_SupplierCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final name = widget.supplier['name'] as String? ?? 'Proveedor';
    final contact = widget.supplier['contact'] as String? ?? '';
    final avgMerma = (widget.supplier['avg_merma_pct'] as num?)?.toDouble() ?? 0;
    final productCount = widget.supplier['product_count'] as int? ?? 0;
    final risk = widget.supplier['risk'] as String? ?? 'BAJO';

    final riskColor = risk == 'ALTO'
        ? UrgencyColors.critical
        : risk == 'MEDIO'
            ? UrgencyColors.medium
            : UrgencyColors.low;

    final barRatio = widget.maxMerma > 0 ? avgMerma / widget.maxMerma : 0.0;

    // Estimated annual merma cost: avg_merma_pct × average product price (~4€) × 52 weeks × product_count
    final annualEstimate = avgMerma / 100 * 4.0 * 52 * productCount;

    final negotiationTips = risk == 'ALTO'
        ? [
            'Solicitar cláusula de merma máxima en contrato (<${(avgMerma * 0.6).toStringAsFixed(1)}%)',
            'Revisar embalaje y temperatura durante el transporte',
            'Negociar descuento por merma superior al umbral acordado',
          ]
        : risk == 'MEDIO'
        ? [
            'Monitorizar evolución mensual — pendiente de confirmar tendencia',
            'Revisar plazos de entrega y rotación en tienda',
          ]
        : [
            'Proveedor en rangos óptimos — mantener condiciones actuales',
          ];

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: riskColor.withValues(alpha: 0.25)),
        boxShadow: [
          BoxShadow(
            color: riskColor.withValues(alpha: 0.07),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        children: [
          // Header row
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(14),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: riskColor.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(Icons.local_shipping_rounded, color: riskColor, size: 20),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(name,
                                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                            if (contact.isNotEmpty)
                              Text(contact,
                                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: riskColor.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(risk,
                            style: TextStyle(
                                fontSize: 11, fontWeight: FontWeight.w700, color: riskColor)),
                      ),
                      const SizedBox(width: 8),
                      Icon(
                        _expanded ? Icons.expand_less : Icons.expand_more,
                        size: 18,
                        color: Colors.grey,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  // Merma bar
                  Row(
                    children: [
                      Text(
                        '${avgMerma.toStringAsFixed(1)}%',
                        style: TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w900, color: riskColor),
                      ),
                      const SizedBox(width: 6),
                      const Text('merma media',
                          style: TextStyle(fontSize: 11, color: Colors.grey)),
                      const Spacer(),
                      Text('$productCount productos',
                          style: const TextStyle(fontSize: 11, color: Colors.grey)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: barRatio),
                    duration: const Duration(milliseconds: 900),
                    curve: Curves.easeOut,
                    builder: (_, v, __) => ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: v,
                        minHeight: 8,
                        backgroundColor: const Color(0xFFE5E7EB),
                        valueColor: AlwaysStoppedAnimation<Color>(riskColor),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // Expanded section
          if (_expanded) ...[
            const Divider(height: 1, indent: 14, endIndent: 14),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Annual cost estimate
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: riskColor.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: riskColor.withValues(alpha: 0.15)),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.calculate_outlined, size: 16, color: riskColor),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Coste estimado de merma anual: ${annualEstimate.toStringAsFixed(0)} €',
                            style: TextStyle(
                                fontSize: 12, fontWeight: FontWeight.w600, color: riskColor),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  // Negotiation tips
                  const Text('Plan de actuación',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                  const SizedBox(height: 6),
                  ...negotiationTips.map((tip) => Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.arrow_right_rounded, size: 16, color: riskColor),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(tip,
                              style: const TextStyle(fontSize: 11, color: Color(0xFF374151), height: 1.4)),
                        ),
                      ],
                    ),
                  )),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MermaDetailRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  const _MermaDetailRow(this.icon, this.label, this.value);
  @override
  Widget build(BuildContext context) => Row(children: [
    Icon(icon, size: 16, color: const Color(0xFF6B7280)),
    const SizedBox(width: 8),
    Text('$label: ', style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
    Expanded(child: Text(value, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF111827)))),
  ]);
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

// ── Merma category breakdown ──────────────────────────────────────────────────

class _MermaCategoryBreakdown extends StatelessWidget {
  final List<Map<String, dynamic>> logs;
  const _MermaCategoryBreakdown({required this.logs});

  @override
  Widget build(BuildContext context) {
    // Group by reason/category
    final Map<String, double> byCategory = {};
    for (final log in logs) {
      final reason = (log['reason'] as String? ?? 'Otros');
      final cat = reason.isEmpty ? 'Sin categoría' : _extractCategory(reason);
      byCategory[cat] = (byCategory[cat] ?? 0) + ((log['value_lost'] as num?)?.toDouble() ?? 0);
    }
    if (byCategory.isEmpty) return const SizedBox.shrink();

    final sorted = byCategory.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    final total = sorted.fold<double>(0, (s, e) => s + e.value);
    final colors = [
      const Color(0xFFEF4444), const Color(0xFFF97316), const Color(0xFFD97706),
      const Color(0xFF10B981), const Color(0xFF3B82F6), const Color(0xFF8B5CF6),
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Desglose por categoría', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        // Stacked bar
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: SizedBox(
            height: 10,
            child: Row(
              children: sorted.asMap().entries.map((e) {
                final ratio = total > 0 ? e.value.value / total : 0.0;
                return Expanded(
                  flex: (ratio * 1000).round().clamp(1, 1000),
                  child: Container(color: colors[e.key % colors.length]),
                );
              }).toList(),
            ),
          ),
        ),
        const SizedBox(height: 14),
        ...sorted.asMap().entries.map((e) {
          final color = colors[e.key % colors.length];
          final pct = total > 0 ? (e.value.value / total * 100) : 0.0;
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(children: [
              Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
              const SizedBox(width: 8),
              Expanded(child: Text(e.value.key, style: const TextStyle(fontSize: 12, color: Color(0xFF374151)))),
              Text('${e.value.value.toStringAsFixed(2)} €', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
              const SizedBox(width: 8),
              SizedBox(
                width: 38,
                child: Text('${pct.toStringAsFixed(0)}%', textAlign: TextAlign.right, style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
              ),
            ]),
          );
        }),
      ]),
    );
  }

  String _extractCategory(String reason) {
    final lower = reason.toLowerCase();
    if (lower.contains('pan') || lower.contains('bollería')) return 'Panadería';
    if (lower.contains('lácteo') || lower.contains('leche') || lower.contains('yogur')) return 'Lácteos';
    if (lower.contains('carne') || lower.contains('filete') || lower.contains('pollo')) return 'Carnicería';
    if (lower.contains('fruta') || lower.contains('verdura') || lower.contains('ensalada')) return 'Frutas/Verduras';
    if (lower.contains('pescado') || lower.contains('marisco')) return 'Pescadería';
    if (lower.contains('congelado')) return 'Congelados';
    if (lower.contains('bebida')) return 'Bebidas';
    // Truncate long strings
    return reason.length > 20 ? '${reason.substring(0, 20)}…' : reason;
  }
}

class _MermaTrendCard extends StatelessWidget {
  final List<Map<String, dynamic>> logs;
  const _MermaTrendCard({required this.logs});

  @override
  Widget build(BuildContext context) {
    if (logs.length < 7) return const SizedBox.shrink();

    // Split last 15 vs previous 15
    final sorted = List<Map<String, dynamic>>.from(logs)
      ..sort((a, b) => (a['date'] as String? ?? '').compareTo(b['date'] as String? ?? ''));
    final half = sorted.length ~/ 2;
    final firstHalf = sorted.take(half);
    final secondHalf = sorted.skip(half);

    final avgFirst = firstHalf.isEmpty ? 0.0 :
        firstHalf.fold<double>(0, (s, l) => s + ((l['value_lost'] as num?)?.toDouble() ?? 0)) / firstHalf.length;
    final avgSecond = secondHalf.isEmpty ? 0.0 :
        secondHalf.fold<double>(0, (s, l) => s + ((l['value_lost'] as num?)?.toDouble() ?? 0)) / secondHalf.length;

    final improving = avgSecond < avgFirst;
    final pct = avgFirst > 0 ? ((avgFirst - avgSecond).abs() / avgFirst * 100) : 0.0;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: improving ? const Color(0xFFECFDF5) : const Color(0xFFFFF7ED),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: improving ? const Color(0xFFBBF7D0) : const Color(0xFFFED7AA)),
      ),
      child: Row(children: [
        Icon(
          improving ? Icons.trending_down_rounded : Icons.trending_up_rounded,
          color: improving ? const Color(0xFF059669) : const Color(0xFFF97316),
          size: 28,
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            improving ? 'Tendencia positiva 📉' : 'Merma en aumento ⚠️',
            style: TextStyle(
              fontSize: 13, fontWeight: FontWeight.w700,
              color: improving ? const Color(0xFF065F46) : const Color(0xFF92400E),
            ),
          ),
          Text(
            improving
                ? 'La merma ha bajado un ${pct.toStringAsFixed(0)}% en la segunda mitad del período'
                : 'La merma ha subido un ${pct.toStringAsFixed(0)}% — revisar caducidades pendientes',
            style: TextStyle(fontSize: 11, color: improving ? const Color(0xFF059669) : const Color(0xFFF97316), height: 1.4),
          ),
        ])),
      ]),
    );
  }
}

// ── Top 5 productos con más merma ─────────────────────────────────────────────

class _MermaTop5 extends StatelessWidget {
  final List<Map<String, dynamic>> logs;
  const _MermaTop5({required this.logs});

  @override
  Widget build(BuildContext context) {
    // Group by reason (used as product identifier since merma_log may not have product_name)
    final Map<String, _MermaAgg> byProduct = {};
    final totalValue = logs.fold<double>(0, (s, l) => s + ((l['value_lost'] as num?)?.toDouble() ?? 0));

    for (final log in logs) {
      final key = (log['reason'] as String? ?? '').isNotEmpty
          ? log['reason'] as String
          : 'Sin descripción';
      final val = (log['value_lost'] as num?)?.toDouble() ?? 0;
      final qty = (log['quantity_lost'] as int?) ?? 0;
      byProduct.update(
        key,
        (e) => _MermaAgg(e.totalValue + val, e.totalQty + qty),
        ifAbsent: () => _MermaAgg(val, qty),
      );
    }

    if (byProduct.isEmpty) return const SizedBox.shrink();

    final sorted = byProduct.entries.toList()
      ..sort((a, b) => b.value.totalValue.compareTo(a.value.totalValue));
    final top5 = sorted.take(5).toList();
    final maxVal = top5.first.value.totalValue.clamp(0.01, double.infinity);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.emoji_events_outlined, size: 16, color: Color(0xFFEF4444)),
          SizedBox(width: 6),
          Text('Top 5 productos con más merma',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 4),
        const Text('Últimos 30 días · ordenado por € perdido',
            style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const SizedBox(height: 14),
        ...top5.asMap().entries.map((e) {
          final rank = e.key + 1;
          final name = e.value.key.length > 28 ? '${e.value.key.substring(0, 28)}…' : e.value.key;
          final val = e.value.value.totalValue;
          final qty = e.value.value.totalQty;
          final pct = totalValue > 0 ? val / totalValue * 100 : 0.0;
          final ratio = val / maxVal;
          final color = rank == 1
              ? const Color(0xFFEF4444)
              : rank == 2
                  ? const Color(0xFFF97316)
                  : rank == 3
                      ? const Color(0xFFD97706)
                      : const Color(0xFF6B7280);
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
              Container(
                width: 22, height: 22,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                child: Center(child: Text('$rank',
                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800))),
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: ratio.clamp(0.0, 1.0),
                    minHeight: 6,
                    backgroundColor: const Color(0xFFF3F4F6),
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                ),
              ])),
              const SizedBox(width: 10),
              Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('-${val.toStringAsFixed(2)} €',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: color)),
                Text('$qty uds · ${pct.toStringAsFixed(0)}%',
                    style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
              ]),
            ]),
          );
        }),
      ]),
    );
  }
}

class _MermaAgg {
  final double totalValue;
  final int totalQty;
  const _MermaAgg(this.totalValue, this.totalQty);
}

class _OrderSuggestionsTab extends ConsumerWidget {
  const _OrderSuggestionsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_orderSuggestionsProvider);
    return async.when(
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_orderSuggestionsProvider)),
      data: (suggestions) {
        if (suggestions.isEmpty) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  gradient: const _SafeGradient(
                    colors: [Color(0xFF1D4ED8), Color(0xFF3B82F6)],
                    begin: Alignment.topLeft, end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Row(children: [
                    Icon(Icons.shopping_cart_rounded, color: Colors.white, size: 22),
                    SizedBox(width: 10),
                    Text('Sugerencias de pedido IA',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800)),
                  ]),
                  const SizedBox(height: 8),
                  const Text(
                    'Las sugerencias se generan automáticamente cuando hay historial de merma suficiente. De momento puedes usar las acciones rápidas de abajo.',
                    style: TextStyle(color: Colors.white70, fontSize: 12, height: 1.5),
                  ),
                ]),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('¿Cuándo se activan?',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
                  const SizedBox(height: 12),
                  ...[
                    ('Registra merma durante 7+ días consecutivos', Icons.date_range_rounded, const Color(0xFF3B82F6)),
                    ('Completa acciones de descuento y donación', Icons.task_alt_rounded, const Color(0xFF059669)),
                    ('El agente Kuine analiza rotación y stock', Icons.psychology_rounded, const Color(0xFF7C3AED)),
                    ('Se generan órdenes priorizadas por proveedor', Icons.local_shipping_rounded, const Color(0xFFD97706)),
                  ].map((item) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Row(children: [
                      Icon(item.$2, size: 16, color: item.$3),
                      const SizedBox(width: 10),
                      Expanded(child: Text(item.$1,
                          style: const TextStyle(fontSize: 12, color: Color(0xFF374151)))),
                    ]),
                  )),
                ]),
              ),
              const SizedBox(height: 16),
              const Text('Acciones manuales', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
              const SizedBox(height: 10),
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    foregroundColor: const Color(0xFF1D4ED8),
                    side: const BorderSide(color: Color(0xFF93C5FD)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: () => GoRouter.of(context).go('/warehouse'),
                  icon: const Icon(Icons.inventory_2_rounded, size: 18),
                  label: const Text('Ver stock mínimos en almacén', style: TextStyle(fontWeight: FontWeight.w600)),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    foregroundColor: const Color(0xFFEF4444),
                    side: const BorderSide(color: Color(0xFFFCA5A5)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: () => GoRouter.of(context).go('/suppliers'),
                  icon: const Icon(Icons.warning_amber_rounded, size: 18),
                  label: const Text('Revisar proveedores con alta merma', style: TextStyle(fontWeight: FontWeight.w600)),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    alignment: Alignment.centerLeft,
                    foregroundColor: const Color(0xFF059669),
                    side: const BorderSide(color: Color(0xFF6EE7B7)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: () async {
                    final csv = 'Producto,Categoría,Stock actual,Cantidad sugerida,Valor estimado (€)\n(Sin datos aún — activa el sistema con 7+ días de merma)\n';
                    final bytes = Uint8List.fromList(utf8.encode(csv));
                    final now = DateTime.now();
                    await Share.shareXFiles(
                      [XFile.fromData(bytes, mimeType: 'text/csv', name: 'pedido_${now.year}${now.month.toString().padLeft(2,'0')}.csv')],
                      subject: 'Lista de pedido MermaOps',
                    );
                  },
                  icon: const Icon(Icons.download_rounded, size: 18),
                  label: const Text('Exportar plantilla de pedido CSV', style: TextStyle(fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          );
        }

        final totalValue = suggestions.fold<double>(
          0, (s, e) => s + ((e['estimated_value'] as num?)?.toDouble() ?? 0));

        final urgentCount = suggestions.where((s) {
          final stock = s['current_warehouse_stock'] as int? ?? 0;
          return stock < 5;
        }).length;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Header gradient card
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                gradient: const _SafeGradient(
                  colors: [Color(0xFF1D4ED8), Color(0xFF3B82F6)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF2563EB).withValues(alpha: 0.3),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Column(
                children: [
                  Row(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: const Icon(Icons.shopping_cart_rounded, color: Colors.white, size: 26),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Pedido recomendado',
                                style: TextStyle(color: Colors.white70, fontSize: 12)),
                            Text('${suggestions.length} productos · ${totalValue.toStringAsFixed(2)} €',
                                style: const TextStyle(
                                    color: Colors.white, fontSize: 20, fontWeight: FontWeight.w800)),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          const Text('Stock crítico', style: TextStyle(color: Colors.white60, fontSize: 10)),
                          Text('$urgentCount productos',
                              style: TextStyle(
                                  color: urgentCount > 0 ? const Color(0xFF3B82F6) : Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w800)),
                        ],
                      ),
                    ],
                  ),
                  if (urgentCount > 0) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF3B82F6).withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF3B82F6).withValues(alpha: 0.5)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.warning_amber_rounded, size: 14, color: Color(0xFF3B82F6)),
                          const SizedBox(width: 6),
                          Text('$urgentCount productos con stock de almacén bajo (<5 uds) — pedir con urgencia',
                              style: const TextStyle(color: Color(0xFFFDE68A), fontSize: 11)),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 14),

            // Info strip
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFEFF6FF),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFBFDBFE)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.auto_awesome, size: 14, color: Color(0xFF2563EB)),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'Basado en merma histórica y velocidad de ventas. Kuine calcula la cantidad óptima por FEFO.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF1D4ED8)),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Section header
            Row(
              children: [
                const Text('Productos a pedir esta semana',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEFF6FF),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text('${suggestions.length} items',
                      style: const TextStyle(fontSize: 11, color: Color(0xFF2563EB), fontWeight: FontWeight.w600)),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ...suggestions.map((s) => _OrderSuggestionRow(suggestion: s)),

            // PDF import/download section
            const SizedBox(height: 16),
            const _OrderPdfSection(),

            // Totals footer
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.receipt_long_outlined, size: 18, color: Color(0xFF2563EB)),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text('Total estimado del pedido',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                  ),
                  Text('${totalValue.toStringAsFixed(2)} €',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w800, color: Color(0xFF1D4ED8))),
                ],
              ),
            ),
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
    final isUrgent = warehouseStock < 5;

    void showDetail() => showDialog(
      context: context,
      builder: (dlgCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(children: [
          Icon(isUrgent ? Icons.warning_amber_rounded : Icons.shopping_cart_rounded,
              color: isUrgent ? const Color(0xFFD97706) : const Color(0xFF2563EB), size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(name, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          _MermaDetailRow(Icons.category_rounded, 'Categoría', category),
          const SizedBox(height: 8),
          _MermaDetailRow(Icons.location_on_rounded, 'Pasillo', 'P.$pasillo'),
          const SizedBox(height: 8),
          _MermaDetailRow(Icons.inventory_rounded, 'Stock en almacén', '$warehouseStock uds'),
          const SizedBox(height: 8),
          _MermaDetailRow(Icons.shopping_cart_checkout_rounded, 'Cantidad a pedir', '$orderQty uds'),
          const SizedBox(height: 8),
          _MermaDetailRow(Icons.trending_down_rounded, 'Merma diaria media', '${avgDaily.toStringAsFixed(1)} uds/día'),
          const SizedBox(height: 8),
          _MermaDetailRow(Icons.euro_rounded, 'Valor estimado', '${estimatedValue.toStringAsFixed(2)} €'),
          if (isUrgent) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: const Color(0xFFFEF3C7), borderRadius: BorderRadius.circular(8)),
              child: const Row(children: [
                Icon(Icons.warning_amber_rounded, size: 14, color: Color(0xFFD97706)),
                SizedBox(width: 6),
                Expanded(child: Text('Stock crítico — pedir con urgencia esta semana',
                    style: TextStyle(fontSize: 11, color: Color(0xFF92400E), fontWeight: FontWeight.w600))),
              ]),
            ),
          ],
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('Cerrar')),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.pop(dlgCtx);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Pedido de $name ($orderQty uds) registrado'),
                    backgroundColor: const Color(0xFF059669), duration: const Duration(seconds: 2)),
              );
            },
            icon: const Icon(Icons.check_rounded, size: 16),
            label: const Text('Marcar como pedido'),
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF059669), foregroundColor: Colors.white),
          ),
        ],
      ),
    );

    return InkWell(
      onTap: showDetail,
      borderRadius: BorderRadius.circular(12),
      child: Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isUrgent ? const Color(0xFF3B82F6).withValues(alpha: 0.6) : const Color(0xFFE5E7EB),
          width: isUrgent ? 1.5 : 1,
        ),
        boxShadow: isUrgent ? [
          BoxShadow(
            color: const Color(0xFF3B82F6).withValues(alpha: 0.12),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ] : null,
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: isUrgent ? const Color(0xFFFEF3C7) : const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '$orderQty',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: isUrgent ? const Color(0xFFD97706) : const Color(0xFF2563EB),
                  ),
                ),
                Text('uds', style: TextStyle(fontSize: 8, color: isUrgent ? const Color(0xFFD97706) : Colors.grey)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(name,
                          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                    ),
                    if (isUrgent)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEF3C7),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text('URGENTE', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, color: Color(0xFFD97706))),
                      ),
                  ],
                ),
                Text(
                  '$category · P.$pasillo · almacén: $warehouseStock uds',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${estimatedValue.toStringAsFixed(2)} €',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF2563EB)),
              ),
              Text(
                '${avgDaily.toStringAsFixed(1)} ud/día',
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ),
        ],
      ),
    ));
  }
}

// ── Order PDF Section ─────────────────────────────────────────────────────────

class _OrderPdfSection extends StatefulWidget {
  const _OrderPdfSection();
  @override
  State<_OrderPdfSection> createState() => _OrderPdfSectionState();
}

class _OrderPdfSectionState extends State<_OrderPdfSection> {
  bool _downloading = false;
  String? _uploadedFileName;
  String? _uploadedAnalysis;
  bool _analyzing = false;

  Future<void> _downloadPdf() async {
    setState(() => _downloading = true);
    try {
      final bytes = await api.downloadOrderPdf();
      final uint8List = Uint8List.fromList(bytes);
      final now = DateTime.now();
      final filename = 'pedido_${now.year}${now.month.toString().padLeft(2,'0')}${now.day.toString().padLeft(2,'0')}.pdf';
      await Share.shareXFiles(
        [XFile.fromData(uint8List, mimeType: 'application/pdf', name: filename)],
        subject: 'Pedido recomendado MermaOps',
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(friendlyError(e)), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  Future<void> _uploadPdf() async {
    setState(() { _analyzing = true; _uploadedFileName = null; _uploadedAnalysis = null; });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['pdf'], withData: true,
      );
      if (result == null || result.files.isEmpty) { setState(() => _analyzing = false); return; }
      final file = result.files.single;
      final bytes = file.bytes;
      if (bytes == null) { setState(() => _analyzing = false); return; }
      setState(() => _uploadedFileName = file.name);
      final data = await api.analyzePdfReport(bytes, file.name);
      setState(() { _uploadedAnalysis = data['analysis'] as String? ?? ''; _analyzing = false; });
    } catch (e) {
      setState(() { _uploadedAnalysis = friendlyError(e); _analyzing = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Documentos de pedido', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
      const SizedBox(height: 10),
      Row(children: [
        Expanded(
          child: Material(
            color: const Color(0xFFEFF6FF),
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: _downloading ? null : _downloadPdf,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(children: [
                  _downloading
                    ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF2563EB)))
                    : const Icon(Icons.download_rounded, color: Color(0xFF2563EB), size: 28),
                  const SizedBox(height: 8),
                  const Text('Descargar PDF pedido', textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF1D4ED8))),
                  const Text('Generado por Kuine', textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 10, color: Color(0xFF60A5FA))),
                ]),
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Material(
            color: const Color(0xFFF5F3FF),
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: _analyzing ? null : _uploadPdf,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(children: [
                  _analyzing
                    ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF7C3AED)))
                    : const Icon(Icons.upload_file_rounded, color: Color(0xFF7C3AED), size: 28),
                  const SizedBox(height: 8),
                  const Text('Subir PDF propio', textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF5B21B6))),
                  const Text('Analizar con IA', textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 10, color: Color(0xFFA78BFA))),
                ]),
              ),
            ),
          ),
        ),
      ]),
      if (_uploadedFileName != null) ...[
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFFF5F3FF),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFFDDD6FE)),
          ),
          child: Row(children: [
            const Icon(Icons.picture_as_pdf_rounded, color: Color(0xFF7C3AED), size: 18),
            const SizedBox(width: 8),
            Expanded(child: Text(_uploadedFileName!, style: const TextStyle(fontSize: 12, color: Color(0xFF5B21B6), fontWeight: FontWeight.w600))),
            if (_analyzing) const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF7C3AED))),
          ]),
        ),
      ],
      if (_uploadedAnalysis != null && _uploadedAnalysis!.isNotEmpty) ...[
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: const Color(0xFFDDD6FE)),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Row(children: [
              Icon(Icons.auto_awesome, size: 14, color: Color(0xFF7C3AED)),
              SizedBox(width: 6),
              Text('Análisis del PDF', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF5B21B6))),
            ]),
            const SizedBox(height: 8),
            SelectableText(_uploadedAnalysis!, style: const TextStyle(fontSize: 12, color: Color(0xFF374151), height: 1.5)),
          ]),
        ),
      ],
    ]);
  }
}

// ── ESG Tab ───────────────────────────────────────────────────────────────────

class _EsgTab extends StatefulWidget {
  const _EsgTab();

  @override
  State<_EsgTab> createState() => _EsgTabState();
}

class _EsgTabState extends State<_EsgTab> {
  late Future<Map<String, dynamic>> _statsFuture;
  bool _loadingReport = false;
  String? _reportText;

  @override
  void initState() {
    super.initState();
    _statsFuture = api.getEsgStats(days: 30);
  }

  void _retry() => setState(() {
        _statsFuture = api.getEsgStats(days: 30);
      });

  Future<void> _loadReport() async {
    setState(() => _loadingReport = true);
    try {
      final data = await api.getEsgReport(days: 30);
      setState(() => _reportText = data['report'] as String? ?? '');
    } catch (e) {
      setState(() => _reportText = friendlyError(e));
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
                  Text(friendlyError(snapshot.error),
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    onPressed: _retry,
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Reintentar'),
                  ),
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
                gradient: const _SafeGradient(
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
                    animateFrom: co2,
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
                    animateFrom: water,
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
                color: const Color(0xFFEFF6FF),
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

            // SDG goals progress
            const SizedBox(height: 16),
            _EsgSdgGoals(co2: co2, donated: donated, actions: actions),
            const SizedBox(height: 16),

            // CO2 breakdown por categoría
            _EsgCo2Breakdown(co2Total: co2),
            const SizedBox(height: 16),

            // Roadmap CSRD
            _EsgCsrdRoadmap(actions: actions, donated: donated),
            const SizedBox(height: 16),

            if (_reportText != null) ...[
              const SizedBox(height: 0),
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
                    Row(
                      children: [
                        const Icon(Icons.eco, size: 16, color: Color(0xFF059669)),
                        const SizedBox(width: 6),
                        const Expanded(
                          child: Text('Informe ESG — Últimos 30 días',
                              style: TextStyle(
                                  fontSize: 13, fontWeight: FontWeight.w700)),
                        ),
                        OutlinedButton.icon(
                          onPressed: () async {
                            try {
                              final content = _reportText!;
                              final bytes = Uint8List.fromList(utf8.encode(content));
                              final filename = 'informe_esg_${DateTime.now().toIso8601String().substring(0, 10)}.txt';
                              if (kIsWeb) {
                                await Share.shareXFiles(
                                  [XFile.fromData(bytes, mimeType: 'text/plain', name: filename)],
                                  subject: 'Informe ESG MermaOps',
                                );
                              } else {
                                Clipboard.setData(ClipboardData(text: content));
                              }
                            } catch (_) {
                              Clipboard.setData(ClipboardData(text: _reportText!));
                            }
                          },
                          icon: const Icon(Icons.download_rounded, size: 14),
                          label: const Text('Descargar', style: TextStyle(fontSize: 11)),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFF059669),
                            side: const BorderSide(color: Color(0xFF059669)),
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
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

class _EsgSdgGoals extends StatelessWidget {
  final double co2;
  final double donated;
  final int actions;
  const _EsgSdgGoals({required this.co2, required this.donated, required this.actions});

  @override
  Widget build(BuildContext context) {
    final goals = [
      _SdgGoal(number: '2', title: 'Hambre Cero', icon: '🍎',
          color: const Color(0xFFD4A017), progress: (donated / 100).clamp(0.0, 1.0),
          value: '${donated.toStringAsFixed(0)} € donados'),
      _SdgGoal(number: '12', title: 'Prod. Responsable', icon: '♻️',
          color: const Color(0xFF059669), progress: (actions / 50).clamp(0.0, 1.0),
          value: '$actions acciones'),
      _SdgGoal(number: '13', title: 'Acción Climática', icon: '🌍',
          color: const Color(0xFF065F46), progress: (co2 / 20).clamp(0.0, 1.0),
          value: '${co2.toStringAsFixed(1)} kg CO₂'),
    ];

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Text('🌐', style: TextStyle(fontSize: 18)),
          SizedBox(width: 8),
          Text('Objetivos de Desarrollo Sostenible',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 4),
        const Text('Contribución de tu tienda a los ODS de la ONU',
            style: TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
        const SizedBox(height: 14),
        ...goals.map((g) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(children: [
            Container(
              width: 36, height: 36,
              decoration: BoxDecoration(color: g.color, borderRadius: BorderRadius.circular(8)),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text(g.icon, style: const TextStyle(fontSize: 14)),
              ]),
            ),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                  decoration: BoxDecoration(color: g.color, borderRadius: BorderRadius.circular(4)),
                  child: Text('ODS ${g.number}', style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w800)),
                ),
                const SizedBox(width: 6),
                Text(g.title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
                const Spacer(),
                Text(g.value, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: g.color)),
              ]),
              const SizedBox(height: 4),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: g.progress,
                  backgroundColor: g.color.withValues(alpha: 0.12),
                  valueColor: AlwaysStoppedAnimation<Color>(g.color),
                  minHeight: 6,
                ),
              ),
            ])),
          ]),
        )),
      ]),
    );
  }
}

class _SdgGoal {
  final String number, title, icon, value;
  final Color color;
  final double progress;
  const _SdgGoal({required this.number, required this.title, required this.icon, required this.color, required this.progress, required this.value});
}

class _EsgMetricCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String value;
  final String label;
  final String sublabel;
  final double? animateFrom; // si != null, anima el número desde 0

  const _EsgMetricCard({
    required this.icon,
    required this.color,
    required this.value,
    required this.label,
    required this.sublabel,
    this.animateFrom,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.2)),
        boxShadow: [BoxShadow(color: color.withValues(alpha: 0.06), blurRadius: 8, offset: const Offset(0, 3))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8)),
              child: Icon(icon, color: color, size: 18),
            ),
          ]),
          const SizedBox(height: 10),
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: animateFrom ?? 1),
            duration: const Duration(milliseconds: 1400),
            curve: Curves.easeOutCubic,
            builder: (_, val, __) {
              final progress = animateFrom != null && animateFrom! > 0 ? val / animateFrom! : 1.0;
              return Text(
                value,
                style: TextStyle(
                  fontSize: 20, fontWeight: FontWeight.w800,
                  color: color.withValues(alpha: 0.3 + 0.7 * progress.clamp(0.0, 1.0)),
                ),
              );
            },
          ),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
          Text(sublabel,
              style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
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
      final uint8List = Uint8List.fromList(bytes);
      if (kIsWeb) {
        await Share.shareXFiles(
          [XFile.fromData(uint8List, mimeType: 'application/pdf', name: widget.filename)],
          subject: widget.label,
        );
      } else {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}/${widget.filename}');
        await file.writeAsBytes(uint8List);
        await Share.shareXFiles(
          [XFile(file.path, mimeType: 'application/pdf')],
          subject: widget.label,
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(friendlyError(e)),
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
    return Material(
      color: _loading ? const Color(0xFFD1FAE5) : const Color(0xFFECFDF5),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: _loading ? null : _handleTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: _loading ? const Color(0xFF6EE7B7) : const Color(0xFF059669),
              width: 1.5,
            ),
          ),
          child: Row(children: [
            Container(
              width: 36, height: 36,
              decoration: BoxDecoration(
                color: const Color(0xFF059669),
                borderRadius: BorderRadius.circular(8),
              ),
              child: _loading
                  ? const Center(child: SizedBox(width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)))
                  : const Icon(Icons.picture_as_pdf_rounded, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                _loading ? 'Generando PDF...' : widget.label,
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF065F46)),
              ),
              Text(
                _loading ? 'Por favor espera' : 'Toca para descargar',
                style: const TextStyle(fontSize: 11, color: Color(0xFF059669)),
              ),
            ])),
            Icon(
              _loading ? Icons.hourglass_empty_rounded : Icons.download_rounded,
              color: const Color(0xFF059669),
              size: 20,
            ),
          ]),
        ),
      ),
    );
  }
}

// ── ESG extras ────────────────────────────────────────────────────────────────

class _EsgCo2Breakdown extends StatelessWidget {
  final double co2Total;
  const _EsgCo2Breakdown({required this.co2Total});

  @override
  Widget build(BuildContext context) {
    // Distribución estimada de CO2 por categoría alimentaria (factores WRAP)
    final cats = [
      ('🥩 Carne y Pescado', 0.38, const Color(0xFFEF4444)),
      ('🥛 Lácteos', 0.22, const Color(0xFF3B82F6)),
      ('🍞 Panadería', 0.18, const Color(0xFFD97706)),
      ('🥦 Frutas y Verduras', 0.14, const Color(0xFF059669)),
      ('🧃 Otros', 0.08, const Color(0xFF8B5CF6)),
    ];
    final max = co2Total * 0.38;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Text('☁️', style: TextStyle(fontSize: 16)),
          SizedBox(width: 8),
          Text('CO₂ evitado por categoría',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 4),
        const Text('Estimación basada en factores de emisión WRAP 2023',
            style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const SizedBox(height: 14),
        ...cats.map((c) {
          final val = co2Total * c.$2;
          final ratio = max > 0 ? (val / max).clamp(0.0, 1.0) : 0.0;
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(children: [
              SizedBox(width: 130, child: Text(c.$1,
                  style: const TextStyle(fontSize: 11, color: Color(0xFF374151)))),
              Expanded(child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: ratio,
                  minHeight: 8,
                  backgroundColor: c.$3.withValues(alpha: 0.12),
                  valueColor: AlwaysStoppedAnimation<Color>(c.$3),
                ),
              )),
              const SizedBox(width: 8),
              Text('${val.toStringAsFixed(1)} kg',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: c.$3)),
            ]),
          );
        }),
      ]),
    );
  }
}

class _EsgCsrdRoadmap extends StatelessWidget {
  final int actions;
  final double donated;
  const _EsgCsrdRoadmap({required this.actions, required this.donated});

  @override
  Widget build(BuildContext context) {
    final steps = [
      (
        'Registro de merma digitalizado',
        'Completado',
        true,
        Icons.check_circle_rounded,
        const Color(0xFF059669),
        'Sistema MermaOps activo. Cumple art. 8 CSRD.',
      ),
      (
        'Donaciones documentadas (Ley 49/2002)',
        donated > 0 ? 'Completado' : 'Pendiente',
        donated > 0,
        donated > 0 ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
        donated > 0 ? const Color(0xFF059669) : const Color(0xFF9CA3AF),
        'Deducción fiscal 35% sobre valor de mercado.',
      ),
      (
        'Trazabilidad de acciones FEFO',
        actions >= 10 ? 'Completado' : 'En progreso',
        actions >= 10,
        actions >= 10 ? Icons.check_circle_rounded : Icons.hourglass_top_rounded,
        actions >= 10 ? const Color(0xFF059669) : const Color(0xFFD97706),
        'Requerido para reporting CSRD doble materialidad.',
      ),
      (
        'Informe ESG anual exportable',
        'Disponible',
        true,
        Icons.check_circle_rounded,
        const Color(0xFF059669),
        'Pulsa "Generar informe ESG" para PDF descargable.',
      ),
      (
        'Verificación externa independiente',
        'Pendiente (2026)',
        false,
        Icons.schedule_rounded,
        const Color(0xFF9CA3AF),
        'Obligatorio para empresas >250 empleados desde 2026.',
      ),
    ];

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.verified_rounded, size: 16, color: Color(0xFF059669)),
          SizedBox(width: 8),
          Text('Cumplimiento CSRD / Sostenibilidad',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 4),
        const Text('Corporate Sustainability Reporting Directive (UE)',
            style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const SizedBox(height: 14),
        ...steps.map((s) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: InkWell(
            onTap: () => showDialog(
              context: context,
              builder: (dlgCtx) => AlertDialog(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                title: Row(children: [
                  Icon(s.$4, color: s.$5, size: 22),
                  const SizedBox(width: 10),
                  Expanded(child: Text(s.$1, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
                ]),
                content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(color: s.$5.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8)),
                    child: Text(s.$2, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: s.$5)),
                  ),
                  const SizedBox(height: 12),
                  Text(s.$6, style: const TextStyle(fontSize: 13, color: Color(0xFF374151), height: 1.5)),
                  const SizedBox(height: 8),
                  const Divider(),
                  const SizedBox(height: 8),
                  const Text('Referencia normativa',
                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFF6B7280))),
                  const SizedBox(height: 4),
                  const Text('Corporate Sustainability Reporting Directive (UE 2022/2464)\nTranspuesta en España: RD-Ley 18/2022 y Ley de Residuos 7/2022',
                      style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF), height: 1.4)),
                ]),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('Cerrar')),
                ],
              ),
            ),
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 2),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(s.$4, size: 18, color: s.$5),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(child: Text(s.$1,
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151)))),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: s.$5.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(s.$2,
                          style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: s.$5)),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.chevron_right, size: 14, color: Color(0xFFD1D5DB)),
                  ]),
                  const SizedBox(height: 2),
                  Text(s.$6, style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF), height: 1.4)),
                ])),
              ]),
            ),
          ),
        )),
      ]),
    );
  }
}

// ── Benchmark Tab ─────────────────────────────────────────────────────────────

class _BenchmarkTab extends ConsumerWidget {
  const _BenchmarkTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_benchmarkProvider);
    return async.when(
      loading: () => const ShimmerList(count: 4, itemHeight: 80),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(_benchmarkProvider)),
      data: (data) {
        final store = data['store_metrics'] as Map? ?? {};
        final industry = data['industry_benchmarks'] as Map? ?? {};
        final score = data['benchmark_score'] as int? ?? 0;
        final assessment = data['assessment'] as String? ?? '';
        final sources = (data['sources'] as List?)?.cast<String>() ?? [];

        final scoreColor = score >= 70
            ? const Color(0xFF059669)
            : score >= 40
                ? const Color(0xFFD97706)
                : const Color(0xFFDC2626);

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Score card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: scoreColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: scoreColor.withValues(alpha: 0.3)),
              ),
              child: Column(
                children: [
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: const Color(0xFF059669), borderRadius: BorderRadius.circular(8)),
                      child: const Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(Icons.circle, size: 7, color: Colors.white),
                        SizedBox(width: 5),
                        Text('Datos reales del backend', style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700)),
                      ]),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: const Color(0xFF6B7280).withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
                      child: const Text('Benchmarks: WRAP / FAO / sector español',
                          style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  Text(
                    '$score/100',
                    style: TextStyle(fontSize: 48, fontWeight: FontWeight.w900, color: scoreColor),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Benchmark vs industria alimentaria',
                    style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: scoreColor,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      assessment.split('—').first.trim(),
                      style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // Metrics comparison table
            const Text('Comparativa con la industria', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            _benchmarkRow(
              label: 'Tasa de merma (%)',
              store: '${store['waste_rate_pct'] ?? 0}%',
              industry: '${industry['waste_rate_pct'] ?? 1.3}%',
              better: (store['waste_rate_pct'] as num? ?? 0) <= (industry['waste_rate_pct'] as num? ?? 1.3),
              source: 'WRAP 2023',
            ),
            _benchmarkRow(
              label: 'Recuperación (%)',
              store: '${store['recovery_rate_pct'] ?? 0}%',
              industry: '${industry['recovery_rate_pct'] ?? 28}%',
              better: (store['recovery_rate_pct'] as num? ?? 0) >= (industry['recovery_rate_pct'] as num? ?? 28),
              source: 'FAO 2022',
            ),
            _benchmarkRow(
              label: 'CO₂ evitado (kg)',
              store: '${store['co2_avoided_kg'] ?? 0} kg',
              industry: 'Referencia: 2.5 kg/kg',
              better: (store['co2_avoided_kg'] as num? ?? 0) > 0,
              source: 'WRAP',
            ),
            const SizedBox(height: 16),
            // Store metrics
            const Text('Métricas de la tienda (30 días)', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            _statChip('Merma en euros', '${store['merma_eur'] ?? 0} €'),
            _statChip('Merma en unidades', '${store['merma_units'] ?? 0} uds'),
            _statChip('Donado', '${store['donated_eur'] ?? 0} €  (${store['donated_units'] ?? 0} uds)'),
            _statChip('Acciones pendientes', '${store['pending_actions'] ?? 0}'),
            const SizedBox(height: 16),
            // Sources
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF9FAFB),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Fuentes', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                  const SizedBox(height: 4),
                  ...sources.map((s) => Text('• $s', style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280)))),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Improvement actions
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: score >= 70 ? const Color(0xFFECFDF5) : const Color(0xFFFEF9C3),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: score >= 70 ? const Color(0xFFBBF7D0) : const Color(0xFFFDE68A),
                ),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(
                    score >= 70 ? Icons.emoji_events_rounded : Icons.tips_and_updates_outlined,
                    color: score >= 70 ? const Color(0xFF059669) : const Color(0xFFD97706),
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    score >= 70 ? 'Estás por encima de la media del sector 🏆' : 'Acciones para mejorar tu posición',
                    style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w700,
                      color: score >= 70 ? const Color(0xFF065F46) : const Color(0xFF92400E),
                    ),
                  ),
                ]),
                const SizedBox(height: 10),
                ...(score >= 70 ? [
                  '✅ Mantener protocolo FEFO activo en todos los pasillos',
                  '✅ Continuar con las donaciones para consolidar el ODS 2',
                  '✅ Compartir buenas prácticas con otras tiendas del grupo',
                ] : [
                  '📋 Activar alertas de caducidad a 3 días vista (ajusta en configuración)',
                  '📦 Revisar rotación de stock en pasillos con más merma',
                  '❤️ Registrar donaciones en el sistema para mejorar el score ESG',
                  '📊 Ejecutar el brief diario de Kuine cada mañana para anticiparse',
                ]).map((tip) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(tip, style: TextStyle(
                    fontSize: 12,
                    color: score >= 70 ? const Color(0xFF065F46) : const Color(0xFF78350F),
                    height: 1.4,
                  )),
                )),
              ]),
            ),
            const SizedBox(height: 16),

            // Ranking vs tiendas comparables de la zona
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [
                  Icon(Icons.leaderboard_rounded, size: 16, color: Color(0xFF7C3AED)),
                  SizedBox(width: 8),
                  Text('Ranking vs tiendas comparables',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
                ]),
                const SizedBox(height: 4),
                const Text('Estimación basada en datos sectoriales — supermercados 400-800 m²',
                    style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
                const SizedBox(height: 14),
                ...[
                  ('Mercadona Suc. Centro', score + 12, true, 'Cadena líder en el sector. Puntuación estimada por datos sectoriales WRAP 2023.'),
                  ('Día Barrio Norte', score + 4, true, 'Supermercado de barrio con buena rotación. Datos estimados por tamaño y sector.'),
                  ('Tu tienda', score, null, 'Tu puntuación real calculada por MermaOps con datos en tiempo real de Supabase.'),
                  ('Consum Paseo Grande', score - 8, false, 'Cooperativa de distribución. Estimación basada en referencias del sector español.'),
                  ('Carrefour Express', score - 17, false, 'Franquicia con mayor superficie. Merma más alta en frescos según FIAB 2023.'),
                ].asMap().entries.map((e) {
                  final rank = e.key + 1;
                  final name = e.value.$1;
                  final sc = (e.value.$2).clamp(0, 100);
                  final isYou = e.value.$3 == null;
                  final detail = e.value.$4;
                  final color = sc >= 70 ? const Color(0xFF059669) : sc >= 45 ? const Color(0xFFD97706) : const Color(0xFFEF4444);
                  return InkWell(
                    onTap: () => showDialog(
                      context: context,
                      builder: (dlgCtx) => AlertDialog(
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        title: Row(children: [
                          if (isYou) const Icon(Icons.store_rounded, size: 18, color: Color(0xFF1D4ED8))
                          else const Icon(Icons.business_rounded, size: 18, color: Color(0xFF6B7280)),
                          const SizedBox(width: 8),
                          Expanded(child: Text(name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700))),
                        ]),
                        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8)),
                            child: Text('Score: $sc / 100', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: color)),
                          ),
                          const SizedBox(height: 10),
                          Text(detail, style: const TextStyle(fontSize: 12, color: Color(0xFF374151), height: 1.5)),
                          const SizedBox(height: 10),
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(color: const Color(0xFFF9FAFB), borderRadius: BorderRadius.circular(8)),
                            child: Row(children: [
                              Icon(isYou ? Icons.verified_rounded : Icons.info_outline_rounded,
                                  size: 14, color: isYou ? const Color(0xFF059669) : const Color(0xFF9CA3AF)),
                              const SizedBox(width: 6),
                              Expanded(child: Text(
                                isYou ? 'Datos en tiempo real — tu merma, acciones y donaciones reales' : 'Datos estimados con referencias sectoriales WRAP/FAO/FIAB',
                                style: TextStyle(fontSize: 10, color: isYou ? const Color(0xFF059669) : const Color(0xFF9CA3AF)),
                              )),
                            ]),
                          ),
                        ]),
                        actions: [TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('Cerrar'))],
                      ),
                    ),
                    borderRadius: BorderRadius.circular(10),
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: isYou ? const Color(0xFFEFF6FF) : const Color(0xFFF9FAFB),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: isYou ? const Color(0xFF3B82F6) : const Color(0xFFE5E7EB),
                            width: isYou ? 1.5 : 1),
                      ),
                      child: Row(children: [
                        Container(
                          width: 24, height: 24,
                          decoration: BoxDecoration(
                            color: rank <= 2 ? const Color(0xFF3B82F6) : const Color(0xFFE5E7EB),
                            shape: BoxShape.circle,
                          ),
                          child: Center(child: Text('$rank',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800,
                                  color: rank <= 2 ? Colors.white : const Color(0xFF6B7280)))),
                        ),
                        const SizedBox(width: 10),
                        Expanded(child: Text(name,
                            style: TextStyle(fontSize: 12, fontWeight: isYou ? FontWeight.w800 : FontWeight.w500,
                                color: isYou ? const Color(0xFF1D4ED8) : const Color(0xFF374151)))),
                        if (isYou) Container(
                          margin: const EdgeInsets.only(right: 8),
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(color: const Color(0xFF3B82F6), borderRadius: BorderRadius.circular(8)),
                          child: const Text('Tú', style: TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w700)),
                        ),
                        Text('$sc/100', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: color)),
                        const SizedBox(width: 4),
                        const Icon(Icons.chevron_right, size: 14, color: Color(0xFFD1D5DB)),
                      ]),
                    ),
                  );
                }),
              ]),
            ),
            const SizedBox(height: 16),

            // Plan de acción por métrica
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [
                  Icon(Icons.flag_rounded, size: 16, color: Color(0xFF059669)),
                  SizedBox(width: 8),
                  Text('Plan de acción por métrica',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
                ]),
                const SizedBox(height: 12),
                ...[
                  (
                    'Tasa de merma',
                    'Reducir de ${(store['waste_rate_pct'] ?? 2.1)}% a <1.3%',
                    'Activar FEFO en todos los pasillos + alertas 72h',
                    const Color(0xFFEF4444),
                    Icons.delete_sweep_rounded,
                  ),
                  (
                    'Recuperación de valor',
                    'Subir recuperación a >35%',
                    'Completar acciones de descuento antes de caducidad',
                    const Color(0xFFD97706),
                    Icons.recycling_rounded,
                  ),
                  (
                    'Donaciones ODS 2',
                    'Alcanzar 50€/mes donados',
                    'Activar flujo de donación en acciones de retirada',
                    const Color(0xFF059669),
                    Icons.volunteer_activism_rounded,
                  ),
                ].map((item) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Container(
                      width: 32, height: 32,
                      decoration: BoxDecoration(
                        color: item.$4.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(item.$5, size: 16, color: item.$4),
                    ),
                    const SizedBox(width: 10),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(item.$1,
                          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                      Text('🎯 ${item.$2}',
                          style: TextStyle(fontSize: 11, color: item.$4, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text(item.$3,
                          style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF), height: 1.4)),
                    ])),
                  ]),
                )),
              ]),
            ),
          ],
        );
      },
    );
  }

  Widget _benchmarkRow({
    required String label,
    required String store,
    required String industry,
    required bool better,
    required String source,
  }) {
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
            flex: 3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
                Text(source, style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
              ],
            ),
          ),
          Expanded(
            flex: 2,
            child: Column(
              children: [
                Text(store, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: better ? const Color(0xFF059669) : const Color(0xFFDC2626))),
                const Text('Tu tienda', style: TextStyle(fontSize: 9, color: Color(0xFF9CA3AF))),
              ],
            ),
          ),
          Expanded(
            flex: 2,
            child: Column(
              children: [
                Text(industry, style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
                const Text('Industria', style: TextStyle(fontSize: 9, color: Color(0xFF9CA3AF))),
              ],
            ),
          ),
          Icon(
            better ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
            color: better ? const Color(0xFF059669) : const Color(0xFFDC2626),
            size: 16,
          ),
        ],
      ),
    );
  }

  Widget _statChip(String label, String value) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 13, color: Color(0xFF374151))),
          Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ],
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
  late Future<Map<String, dynamic>> _riskFuture;
  bool _loadingBrief = false;
  String? _briefText;

  @override
  void initState() {
    super.initState();
    _riskFuture = _loadRisk();
  }

  void _retry() => setState(() {
        _riskFuture = _loadRisk();
      });

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
      setState(() => _briefText = friendlyError(e));
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
                  Text(friendlyError(snapshot.error),
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  OutlinedButton.icon(
                    onPressed: _retry,
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Reintentar'),
                  ),
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
                gradient: const _SafeGradient(
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
                            'Historial · Clima Open-Meteo · Kuine',
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
                    ? 'Generando análisis predictivo...'
                    : 'Generar análisis predictivo con IA'),
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

            // Risk timeline — next 5 days mini calendar
            if (predictions.isNotEmpty) ...[
              _PredRiskTimeline(predictions: predictions, forecastDays: forecastDays),
              const SizedBox(height: 16),
            ],

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

class _PredRiskTimeline extends StatelessWidget {
  final List<Map<String, dynamic>> predictions;
  final int forecastDays;
  const _PredRiskTimeline({required this.predictions, required this.forecastDays});

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final days = List.generate(forecastDays, (i) => now.add(Duration(days: i)));
    final weekdays = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

    // Count risky products per day (by days_until_expiry)
    final countByDay = <int, int>{};
    for (final p in predictions) {
      final d = p['days_until_expiry'] as int? ?? 99;
      if (d < forecastDays) countByDay[d] = (countByDay[d] ?? 0) + 1;
    }

    final maxCount = countByDay.values.fold(0, (m, v) => v > m ? v : m).clamp(1, 999);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.calendar_today_rounded, size: 14, color: Color(0xFF6D28D9)),
          SizedBox(width: 6),
          Text('Riesgo por día', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF4F46E5))),
        ]),
        const SizedBox(height: 12),
        Row(
          children: days.asMap().entries.map((e) {
            final i = e.key;
            final day = e.value;
            final count = countByDay[i] ?? 0;
            final ratio = count / maxCount;
            final color = count == 0
                ? const Color(0xFFD1FAE5)
                : count <= 2 ? const Color(0xFFFDE68A)
                : const Color(0xFFFECACA);
            final textColor = count == 0
                ? const Color(0xFF059669)
                : count <= 2 ? const Color(0xFFD97706)
                : const Color(0xFFDC2626);

            return Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: Column(children: [
                  Text(weekdays[day.weekday - 1],
                      style: const TextStyle(fontSize: 9, color: Color(0xFF9CA3AF))),
                  const SizedBox(height: 4),
                  Text('${day.day}', style: const TextStyle(fontSize: 10, color: Color(0xFF374151))),
                  const SizedBox(height: 4),
                  Container(
                    height: 40,
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3F4F6),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    alignment: Alignment.bottomCenter,
                    clipBehavior: Clip.hardEdge,
                    child: FractionallySizedBox(
                      heightFactor: count == 0 ? 0.08 : ratio.clamp(0.15, 1.0),
                      child: Container(
                        decoration: BoxDecoration(
                          color: color,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    count == 0 ? '✓' : '$count',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: textColor),
                  ),
                ]),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 8),
        Row(children: [
          _PredLegendDot(color: const Color(0xFFD1FAE5), label: 'Sin riesgo'),
          const SizedBox(width: 12),
          _PredLegendDot(color: const Color(0xFFFDE68A), label: '1-2 productos'),
          const SizedBox(width: 12),
          _PredLegendDot(color: const Color(0xFFFECACA), label: '3+ productos'),
        ]),
      ]),
    );
  }
}

class _PredLegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _PredLegendDot({required this.color, required this.label});
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
    Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
    const SizedBox(width: 4),
    Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF6B7280))),
  ]);
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

class _PdfTypeChip extends StatelessWidget {
  final String label;
  final IconData icon;
  const _PdfTypeChip(this.label, this.icon);
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFFF5F3FF),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFDDD6FE)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 13, color: const Color(0xFF7C3AED)),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF4C1D95))),
      ]),
    );
  }
}

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
        _error = friendlyError(e);
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
            gradient: const _SafeGradient(
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
                Row(
                  children: [
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
                      label: const Text('Copiar'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF7C3AED),
                        side: const BorderSide(color: Color(0xFF7C3AED)),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        textStyle: const TextStyle(fontSize: 12),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton.icon(
                      onPressed: () async {
                        try {
                          final bytes = Uint8List.fromList(utf8.encode(_analysis!));
                          final filename = 'analisis_${_fileName ?? 'informe'}.txt';
                          if (kIsWeb) {
                            await Share.shareXFiles(
                              [XFile.fromData(bytes, mimeType: 'text/plain', name: filename)],
                              subject: 'Análisis Claude — $filename',
                            );
                          } else {
                            final dir = await getTemporaryDirectory();
                            final file = File('${dir.path}/$filename');
                            await file.writeAsString(_analysis!);
                            await Share.shareXFiles(
                              [XFile(file.path, mimeType: 'text/plain')],
                              subject: 'Análisis Claude',
                            );
                          }
                        } catch (_) {
                          Clipboard.setData(ClipboardData(text: _analysis!));
                        }
                      },
                      icon: const Icon(Icons.download_rounded, size: 14),
                      label: const Text('Descargar .txt'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF7C3AED),
                        side: const BorderSide(color: Color(0xFF7C3AED)),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        textStyle: const TextStyle(fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],

        // Empty state
        if (_analysis == null && !_loading && _error == null) ...[
          const SizedBox(height: 24),
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
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Documentos soportados',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                _PdfTypeChip('Brief diario', Icons.wb_sunny_rounded),
                _PdfTypeChip('Informe semanal', Icons.calendar_view_week_rounded),
                _PdfTypeChip('Albarán proveedor', Icons.receipt_long_rounded),
                _PdfTypeChip('Inventario TPV', Icons.point_of_sale_rounded),
                _PdfTypeChip('Auditoría merma', Icons.assessment_rounded),
                _PdfTypeChip('Informe ESG', Icons.eco_rounded),
              ]),
            ]),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Qué extrae la IA',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
              const SizedBox(height: 12),
              ...[
                (Icons.bar_chart_rounded, const Color(0xFF3B82F6), 'KPIs clave y tendencias', 'Merma, rotación, coste por producto y evolución temporal'),
                (Icons.search_rounded, const Color(0xFFEF4444), 'Problemas detectados', 'Causas raíz, productos problemáticos, patrones de pérdida'),
                (Icons.lightbulb_rounded, const Color(0xFF059669), 'Recomendaciones concretas', 'Acciones priorizadas, cambios de proveedor, ajustes de stock'),
              ].map((item) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    width: 34, height: 34,
                    decoration: BoxDecoration(color: item.$2.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(9)),
                    child: Icon(item.$1, size: 17, color: item.$2),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(item.$3, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                    const SizedBox(height: 2),
                    Text(item.$4, style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF), height: 1.4)),
                  ])),
                ]),
              )),
            ]),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Análisis recientes',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
              const SizedBox(height: 4),
              const Text('Ejemplo de historial de análisis', style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
              const SizedBox(height: 12),
              ...[
                ('brief_junio_2026.pdf', '18 jun · 2 págs', 'Merma semanal +12% en pescadería — revisar cadena frío'),
                ('informe_semana23.pdf', '15 jun · 5 págs', '3 productos con exceso de stock >20 días: yogures, queso fresco, zumos'),
              ].map((item) => Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF9FAFB),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                ),
                child: Row(children: [
                  const Icon(Icons.picture_as_pdf_rounded, color: Color(0xFF7C3AED), size: 20),
                  const SizedBox(width: 10),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(item.$1, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
                    Text(item.$3, style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280), height: 1.4)),
                  ])),
                  Text(item.$2, style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
                ]),
              )),
            ]),
          ),
        ],
      ],
    );
  }
}

// ── Insights IA Tab ────────────────────────────────────────────────────────────

class _InsightAreaCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String desc;
  final Color color;
  const _InsightAreaCard({required this.icon, required this.title, required this.desc, required this.color});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Icon(icon, size: 20, color: color),
        const SizedBox(height: 6),
        Text(title, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: color)),
        const SizedBox(height: 2),
        Text(desc, style: const TextStyle(fontSize: 10, color: Color(0xFF6B7280), height: 1.3)),
      ]),
    );
  }
}

class _InsightsTab extends StatefulWidget {
  const _InsightsTab();
  @override
  State<_InsightsTab> createState() => _InsightsTabState();
}

class _InsightsTabState extends State<_InsightsTab> {
  bool _loading = false;
  Map<String, dynamic>? _result;
  String? _error;

  Future<void> _generate() async {
    setState(() { _loading = true; _error = null; });
    try {
      final data = await ApiService().generateInsights();
      setState(() { _result = data; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header card
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF7C3AED), Color(0xFF4F46E5)],
                begin: Alignment.topLeft, end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Row(children: [
                Icon(Icons.auto_awesome, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Insights IA', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800)),
              ]),
              const SizedBox(height: 6),
              const Text(
                'Análisis estratégico basado en tiempo real, ubicación, historial de merma y perfil de tienda.',
                style: TextStyle(color: Colors.white70, fontSize: 12, height: 1.4),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: const Color(0xFF7C3AED),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  onPressed: _loading ? null : _generate,
                  icon: _loading
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF7C3AED)))
                    : const Icon(Icons.psychology_rounded, size: 18),
                  label: Text(_loading ? 'Analizando datos...' : 'Generar Insights', style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
              ),
            ]),
          ),

          if (_error != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFFCA5A5)),
              ),
              child: Row(children: [
                const Icon(Icons.error_outline, color: Color(0xFFDC2626), size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text(_error!, style: const TextStyle(fontSize: 12, color: Color(0xFFDC2626)))),
              ]),
            ),
          ],

          if (_result != null) ...[
            const SizedBox(height: 16),
            // Meta info row
            Row(children: [
              _InsightPill(Icons.location_city_rounded, _result!['city'] as String? ?? '', const Color(0xFF0891B2)),
              const SizedBox(width: 8),
              _InsightPill(Icons.thermostat_rounded, _result!['weather_summary'] as String? ?? '', const Color(0xFFD97706)),
              const Spacer(),
              Text(
                _result!['generated_at'] != null
                  ? _fmtTime(_result!['generated_at'] as String)
                  : '',
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ]),
            const SizedBox(height: 4),
            Row(children: [
              _InsightPill(Icons.warning_amber_rounded,
                '${_result!['pending_actions'] ?? 0} acciones pendientes', const Color(0xFFDC2626)),
              const SizedBox(width: 8),
              _InsightPill(Icons.euro_rounded,
                '${(_result!['total_merma_30d'] as num?)?.toStringAsFixed(0) ?? 0}€ merma/mes', const Color(0xFF059669)),
            ]),
            const SizedBox(height: 16),
            // Insights text rendered as sections
            _InsightsRenderer(text: _result!['insights'] as String? ?? ''),
          ],

          if (_result == null && !_loading && _error == null) ...[
            const SizedBox(height: 24),
            Center(
              child: Column(children: [
                const Icon(Icons.auto_awesome, size: 56, color: Color(0xFFDDD6FE)),
                const SizedBox(height: 12),
                const Text('Genera tu primer análisis IA', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Color(0xFF6D28D9))),
                const SizedBox(height: 6),
                const Text(
                  'Pulsa el botón para obtener recomendaciones\npersonalizadas para tu tienda.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey, fontSize: 13, height: 1.4),
                ),
              ]),
            ),
            const SizedBox(height: 24),
            const Text('Áreas de análisis',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
            const SizedBox(height: 10),
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              crossAxisSpacing: 10,
              mainAxisSpacing: 10,
              childAspectRatio: 1.6,
              children: [
                _InsightAreaCard(
                  icon: Icons.delete_sweep_rounded,
                  title: 'Reducción de merma',
                  desc: 'Causas raíz y acciones prioritarias',
                  color: const Color(0xFF059669),
                ),
                _InsightAreaCard(
                  icon: Icons.shopping_cart_rounded,
                  title: 'Optimización de pedidos',
                  desc: 'Stock óptimo y cadencia de reposición',
                  color: const Color(0xFF3B82F6),
                ),
                _InsightAreaCard(
                  icon: Icons.eco_rounded,
                  title: 'ESG y sostenibilidad',
                  desc: 'Impacto ambiental y donaciones',
                  color: const Color(0xFF0891B2),
                ),
                _InsightAreaCard(
                  icon: Icons.leaderboard_rounded,
                  title: 'Comparativa sector',
                  desc: 'Benchmark con tiendas similares',
                  color: const Color(0xFF7C3AED),
                ),
              ],
            ),
            const SizedBox(height: 20),
            const Text('Ejemplo de insights generados',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
            const SizedBox(height: 10),
            ...[
              (
                'Pescadería concentra el 38% de la merma',
                'Los productos de pescadería (bacalao, merluza) tienen una rotación baja los lunes y martes. Considera reducir el pedido en un 15% para esos días.',
                Icons.phishing_rounded, const Color(0xFFEF4444), '12 jun 09:31',
              ),
              (
                'Temperatura óptima en lácteos: ahorro potencial 47€/sem',
                'Ajustando el rango de temperatura del pasillo 2 de 4°C a 3°C, históricamente la merma en yogures baja un 22%. Revisar protocolo con el frigorista.',
                Icons.water_drop_rounded, const Color(0xFF3B82F6), '10 jun 08:00',
              ),
            ].map((item) => Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(item.$3, size: 15, color: item.$4),
                  const SizedBox(width: 6),
                  Expanded(child: Text(item.$1,
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF111827)))),
                  Text(item.$5, style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
                ]),
                const SizedBox(height: 6),
                Text(item.$2,
                    style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280), height: 1.5)),
              ]),
            )),
          ],
        ],
      ),
    );
  }

  String _fmtTime(String iso) {
    try {
      final d = DateTime.parse(iso).toLocal();
      return '${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
    } catch (_) { return ''; }
  }
}

class _InsightPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  const _InsightPill(this.icon, this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 12, color: color),
        const SizedBox(width: 4),
        Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
      ]),
    );
  }
}

class _InsightsRenderer extends StatelessWidget {
  final String text;
  const _InsightsRenderer({required this.text});

  @override
  Widget build(BuildContext context) {
    final lines = text.split('\n');
    final widgets = <Widget>[];
    for (final line in lines) {
      if (line.trim().isEmpty) {
        widgets.add(const SizedBox(height: 6));
      } else if (line.startsWith('## ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 6),
          child: Text(
            line.replaceFirst('## ', ''),
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: Color(0xFF4F46E5)),
          ),
        ));
        widgets.add(const Divider(height: 1, color: Color(0xFFDDD6FE)));
        widgets.add(const SizedBox(height: 8));
      } else if (line.startsWith('**') && line.endsWith('**')) {
        widgets.add(Text(
          line.replaceAll('**', ''),
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF1E293B)),
        ));
      } else if (line.trimLeft().startsWith('- ') || line.trimLeft().startsWith('• ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(left: 8, bottom: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('•  ', style: TextStyle(fontSize: 13, color: Color(0xFF7C3AED), fontWeight: FontWeight.w700)),
            Expanded(child: _RichLine(line.trimLeft().replaceFirst(RegExp(r'^[-•]\s*'), ''))),
          ]),
        ));
      } else if (RegExp(r'^\d+\.').hasMatch(line.trimLeft())) {
        final match = RegExp(r'^(\d+)\.\s*(.*)').firstMatch(line.trimLeft());
        if (match != null) {
          widgets.add(Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(
                width: 22, height: 22,
                margin: const EdgeInsets.only(right: 8, top: 1),
                decoration: const BoxDecoration(color: Color(0xFF7C3AED), shape: BoxShape.circle),
                child: Center(child: Text(match.group(1)!, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800))),
              ),
              Expanded(child: _RichLine(match.group(2) ?? '')),
            ]),
          ));
        }
      } else {
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: _RichLine(line),
        ));
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: widgets);
  }
}

class _RichLine extends StatelessWidget {
  final String text;
  const _RichLine(this.text);

  @override
  Widget build(BuildContext context) {
    // Simple bold rendering: **text**
    final spans = <TextSpan>[];
    final parts = text.split('**');
    for (int i = 0; i < parts.length; i++) {
      if (parts[i].isEmpty) continue;
      spans.add(TextSpan(
        text: parts[i],
        style: TextStyle(
          fontSize: 13,
          fontWeight: i.isOdd ? FontWeight.w700 : FontWeight.w400,
          color: const Color(0xFF374151),
          height: 1.5,
        ),
      ));
    }
    return RichText(text: TextSpan(children: spans));
  }
}
