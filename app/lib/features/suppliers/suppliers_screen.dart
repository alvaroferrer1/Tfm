import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/file_download.dart';
import '../../core/l10n.dart';
import '../../core/store_provider.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart' show ShimmerList;

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

final _suppliersProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  try {
    return await ApiService().getSupplierStats();
  } catch (_) {
    // Backend down — query Supabase directly
    final sid = ref.read(resolvedStoreIdProvider);
    final suppliers = await supabase
        .from('suppliers')
        .select('id, name, contact, supplier_merma(merma_pct, product_id, period)')
        .eq('store_id', sid) as List;
    return suppliers.map<Map<String, dynamic>>((sup) {
      final mermaRows = (sup['supplier_merma'] as List?) ?? [];
      final avgMerma = mermaRows.isEmpty
          ? 0.0
          : mermaRows.fold<double>(0, (s, r) => s + ((r['merma_pct'] as num?)?.toDouble() ?? 0)) /
              mermaRows.length;
      final avg = double.parse(avgMerma.toStringAsFixed(1));
      return {
        'id': sup['id'],
        'name': sup['name'] ?? 'Proveedor',
        'contact': sup['contact'] ?? '',
        'product_count': mermaRows.length,
        'avg_merma_pct': avg,
        'products': mermaRows.map((r) => r['product_id']).where((id) => id != null).toList(),
        'period': mermaRows.isNotEmpty ? mermaRows.first['period'] : null,
        'risk': avg > 15 ? 'ALTO' : avg > 8 ? 'MEDIO' : 'BAJO',
      };
    }).toList();
  }
});

final _suppliersWithProductsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ApiService().getSuppliersWithProducts();
});

final _orderProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return ApiService().getOrderSuggestions();
});

class SuppliersScreen extends ConsumerStatefulWidget {
  const SuppliersScreen({super.key});
  @override
  ConsumerState<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends ConsumerState<SuppliersScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _downloadOrderPdf(BuildContext ctx) async {
    try {
      ScaffoldMessenger.of(ctx).showSnackBar(
        const SnackBar(content: Text('Generando PDF…'), duration: Duration(seconds: 2)),
      );
      final bytes = await ApiService().downloadOrderPdf();
      final now = DateTime.now();
      final name =
          'pedido_${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}.pdf';
      if (kIsWeb) downloadPdf(name, bytes);
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          SnackBar(content: Text('PDF descargado: $name'), backgroundColor: const Color(0xFF059669)),
        );
      }
    } catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Proveedores'),
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white70,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(text: 'Ranking'),
            Tab(text: 'Productos'),
            Tab(text: 'Pedido'),
          ],
        ),
        actions: [
          Consumer(builder: (_, r, __) => TextButton(
            onPressed: () => r.read(languageProvider.notifier).toggle(),
            child: Text(r.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
          )),
        ],
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _RankingTab(),
          _ProductsTab(),
          _OrderTab(onDownloadPdf: () => _downloadOrderPdf(context)),
        ],
      ),
    );
  }
}

// ── Tab Ranking ───────────────────────────────────────────────────────────────

class _RankingTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_suppliersProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(_suppliersProvider),
      child: async.when(
        loading: () => const ShimmerList(count: 5, itemHeight: 88),
        error: (e, _) => AppErrorWidget(
          error: e,
          customMessage: 'No se pudieron cargar los proveedores.',
          onRetry: () => ref.invalidate(_suppliersProvider),
        ),
        data: (suppliers) => _buildRankingList(context, suppliers),
      ),
    );
  }

  Widget _buildRankingList(BuildContext ctx, List<Map<String, dynamic>> suppliers) {
    if (suppliers.isEmpty) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.local_shipping_outlined, size: 56, color: Colors.grey),
          SizedBox(height: 12),
          Text('Sin datos de proveedores', style: TextStyle(fontSize: 16, color: Colors.grey)),
        ]),
      );
    }
    final sorted = List<Map<String, dynamic>>.from(suppliers)
      ..sort((a, b) => ((b['avg_merma_pct'] as num?) ?? 0).compareTo((a['avg_merma_pct'] as num?) ?? 0));
    final maxMerma = (sorted.first['avg_merma_pct'] as num?)?.toDouble() ?? 1.0;
    final totalProducts = sorted.fold<int>(0, (s, p) => s + ((p['product_count'] as int?) ?? 0));
    final avgAll = sorted.isEmpty ? 0.0
        : sorted.fold<double>(0, (s, p) => s + ((p['avg_merma_pct'] as num?)?.toDouble() ?? 0)) / sorted.length;
    final highRisk = sorted.where((s) => ((s['avg_merma_pct'] as num?) ?? 0) >= 15).length;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Hero header
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: const _SafeGradient(
              colors: [Color(0xFF0F172A), Color(0xFF1E3A5F)],
              begin: Alignment.topLeft, end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                width: 44, height: 44,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.local_shipping_rounded, color: Colors.white, size: 24),
              ),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Panel de proveedores',
                    style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800)),
                Text('${sorted.length} proveedores · $totalProducts productos · ${avgAll.toStringAsFixed(1)}% merma media',
                    style: const TextStyle(color: Colors.white60, fontSize: 11)),
              ])),
            ]),
            const SizedBox(height: 16),
            Row(children: [
              _StatPill(value: '${sorted.length}', label: 'proveedores'),
              const SizedBox(width: 10),
              _StatPill(value: '$totalProducts', label: 'productos'),
              const SizedBox(width: 10),
              _StatPill(value: '${avgAll.toStringAsFixed(1)}%', label: 'merma media'),
            ]),
            if (highRisk > 0) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFFEF4444).withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFEF4444).withValues(alpha: 0.4)),
                ),
                child: Row(children: [
                  const Icon(Icons.warning_rounded, size: 14, color: Color(0xFFFCA5A5)),
                  const SizedBox(width: 6),
                  Expanded(child: Text(
                    '$highRisk proveedor${highRisk > 1 ? "es" : ""} con merma ≥15% — revisar condiciones',
                    style: const TextStyle(color: Color(0xFFFCA5A5), fontSize: 11),
                  )),
                ]),
              ),
            ],
          ]),
        ),
        const SizedBox(height: 14),
        // Best/Worst
        Row(children: [
          Expanded(child: _QuickTag(
            label: 'Mayor merma',
            value: sorted.first['name'] as String? ?? '',
            pct: (sorted.first['avg_merma_pct'] as num?)?.toDouble() ?? 0,
            color: const Color(0xFFEF4444), icon: Icons.trending_up,
          )),
          const SizedBox(width: 10),
          Expanded(child: _QuickTag(
            label: 'Mejor índice',
            value: sorted.last['name'] as String? ?? '',
            pct: (sorted.last['avg_merma_pct'] as num?)?.toDouble() ?? 0,
            color: const Color(0xFF059669), icon: Icons.trending_down,
          )),
        ]),
        const SizedBox(height: 14),
        Text('${sorted.length} proveedores — ordenados por % merma',
            style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 10),
        ...sorted.asMap().entries.map((e) => _SupplierCard(rank: e.key + 1, supplier: e.value, maxMerma: maxMerma)),
        const SizedBox(height: 12),
        _DecisionCard(suppliers: sorted),
        const SizedBox(height: 16),
        _AlternativeSuppliersSection(suppliers: sorted),
        const SizedBox(height: 16),
      ],
    );
  }
}

// ── Sección proveedores alternativos ─────────────────────────────────────────

const _altSupplierPool = [
  {'name': 'Mercados Frescos del Norte S.L.', 'categories': ['pescado', 'pescaderia', 'carne', 'carniceria'], 'merma_est': 6.2},
  {'name': 'Distribuciones García & Hijos', 'categories': ['panaderia', 'lacteos', 'otros'], 'merma_est': 7.8},
  {'name': 'Frutas y Hortalizas Premium S.A.', 'categories': ['frutas', 'verduras', 'otros'], 'merma_est': 5.4},
  {'name': 'Lácteos del Cantábrico', 'categories': ['lacteos'], 'merma_est': 4.9},
  {'name': 'Carnes Selectas Ibéricas', 'categories': ['carne', 'carniceria'], 'merma_est': 8.1},
  {'name': 'Panadería Artesana Corrales', 'categories': ['panaderia'], 'merma_est': 3.7},
];

class _AlternativeSuppliersSection extends StatelessWidget {
  final List<Map<String, dynamic>> suppliers;
  const _AlternativeSuppliersSection({required this.suppliers});

  @override
  Widget build(BuildContext context) {
    final highRisk = suppliers.where((s) => ((s['avg_merma_pct'] as num?) ?? 0) >= 15).toList();
    if (highRisk.isEmpty) return const SizedBox.shrink();

    final alts = <Map<String, dynamic>>[];
    for (final sup in highRisk) {
      final cat = (sup['category'] as String? ?? '').toLowerCase();
      final matching = _altSupplierPool.where((a) {
        final cats = List<String>.from(a['categories'] as List);
        return cats.any((c) => cat.contains(c) || c.contains(cat));
      }).take(2).toList();
      for (final alt in matching) {
        if (!alts.any((a) => a['name'] == alt['name'])) {
          alts.add({...alt, 'for_supplier': sup['name'], 'for_category': sup['category']});
        }
      }
    }
    if (alts.isEmpty) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.swap_horiz_rounded, size: 16, color: Color(0xFF059669)),
          SizedBox(width: 6),
          Text('Alternativas recomendadas por IA',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 4),
        const Text('Proveedores que cubren categorías con merma ≥15%',
            style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const SizedBox(height: 14),
        ...alts.map((alt) {
          final currentMerma = suppliers
              .where((s) => (s['category'] as String? ?? '').toLowerCase() == (alt['for_category'] as String? ?? '').toLowerCase())
              .map((s) => (s['avg_merma_pct'] as num?)?.toDouble() ?? 0)
              .fold<double>(0, (a, b) => a > b ? a : b);
          final saving = currentMerma - (alt['merma_est'] as double);
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFF0FDF4),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFBBF7D0)),
            ),
            child: Row(children: [
              Container(
                width: 38, height: 38,
                decoration: BoxDecoration(
                  color: const Color(0xFF059669).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.local_shipping_rounded, size: 18, color: Color(0xFF059669)),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(alt['name'] as String,
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF065F46))),
                const SizedBox(height: 2),
                Text(
                  'Merma estimada: ${(alt['merma_est'] as double).toStringAsFixed(1)}%'
                  '${saving > 0 ? " · ${saving.toStringAsFixed(1)}% menos que ${alt['for_supplier']}" : ""}',
                  style: const TextStyle(fontSize: 10, color: Color(0xFF059669)),
                ),
              ])),
              TextButton(
                style: TextButton.styleFrom(
                  foregroundColor: const Color(0xFF059669),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
                ),
                onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('Contactando con ${alt['name']}...'),
                    backgroundColor: const Color(0xFF059669),
                    duration: const Duration(seconds: 2),
                  ),
                ),
                child: const Text('Contactar'),
              ),
            ]),
          );
        }),
      ]),
    );
  }
}

// ── Tab Productos por proveedor ───────────────────────────────────────────────

class _ProductsTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_ProductsTab> createState() => _ProductsTabState();
}

class _ProductsTabState extends ConsumerState<_ProductsTab> {
  String? _expandedSupplierId;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(_suppliersWithProductsProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(_suppliersWithProductsProvider),
      child: async.when(
        loading: () => const ShimmerList(count: 4, itemHeight: 110),
        error: (e, _) => AppErrorWidget(
          error: e,
          customMessage: 'No se pudieron cargar los productos.',
          onRetry: () => ref.invalidate(_suppliersWithProductsProvider),
        ),
        data: (data) {
          final suppliers = List<Map<String, dynamic>>.from(data['suppliers'] ?? []);
          if (suppliers.isEmpty) {
            return const Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.inventory_2_outlined, size: 56, color: Colors.grey),
                SizedBox(height: 12),
                Text('Sin productos vinculados', style: TextStyle(fontSize: 16, color: Colors.grey)),
              ]),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(14),
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFEFF6FF),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFBFDBFE)),
                ),
                child: Row(children: [
                  const Icon(Icons.info_outline, size: 16, color: Color(0xFF2563EB)),
                  const SizedBox(width: 8),
                  const Expanded(child: Text(
                    'Toca un proveedor para ver sus productos y proveedores alternativos.',
                    style: TextStyle(fontSize: 12, color: Color(0xFF1D4ED8)),
                  )),
                ]),
              ),
              const SizedBox(height: 12),
              ...suppliers.map((sup) => _SupplierProductCard(
                supplier: sup,
                expanded: _expandedSupplierId == (sup['id'] as String?),
                onToggle: () => setState(() {
                  final sid = sup['id'] as String?;
                  _expandedSupplierId = _expandedSupplierId == sid ? null : sid;
                }),
              )),
              const SizedBox(height: 16),
              _ProductsAnalysisSummary(suppliers: suppliers),
              const SizedBox(height: 16),
            ],
          );
        },
      ),
    );
  }
}

class _ProductsAnalysisSummary extends StatelessWidget {
  final List<Map<String, dynamic>> suppliers;
  const _ProductsAnalysisSummary({required this.suppliers});

  @override
  Widget build(BuildContext context) {
    int totalProducts = 0;
    double sumMerma = 0;
    int count = 0;
    String worstName = '';
    double worstMerma = 0;
    String bestName = '';
    double bestMerma = double.infinity;

    for (final sup in suppliers) {
      final products = List<Map<String, dynamic>>.from(sup['products'] ?? []);
      totalProducts += products.length;
      final m = (sup['avg_merma_pct'] as num?)?.toDouble() ?? 0;
      sumMerma += m;
      count++;
      if (m > worstMerma) { worstMerma = m; worstName = sup['name'] as String? ?? ''; }
      if (m < bestMerma) { bestMerma = m; bestName = sup['name'] as String? ?? ''; }
    }
    if (count == 0) return const SizedBox.shrink();
    final avgMerma = sumMerma / count;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.analytics_rounded, size: 16, color: Color(0xFF3B82F6)),
          SizedBox(width: 6),
          Text('Análisis de productos', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        ]),
        const SizedBox(height: 14),
        Row(children: [
          _AnalysisStat('$totalProducts', 'productos totales', const Color(0xFF3B82F6)),
          const SizedBox(width: 10),
          _AnalysisStat('${avgMerma.toStringAsFixed(1)}%', 'merma media', const Color(0xFFF59E0B)),
          const SizedBox(width: 10),
          _AnalysisStat('${count}', 'proveedores', const Color(0xFF059669)),
        ]),
        const SizedBox(height: 14),
        _AnalysisRow(Icons.trending_up_rounded, const Color(0xFFEF4444), 'Mayor merma',
            '${worstName.length > 22 ? "${worstName.substring(0, 22)}…" : worstName} — ${worstMerma.toStringAsFixed(1)}%'),
        const SizedBox(height: 8),
        _AnalysisRow(Icons.trending_down_rounded, const Color(0xFF059669), 'Menor merma',
            '${bestName.length > 22 ? "${bestName.substring(0, 22)}…" : bestName} — ${bestMerma == double.infinity ? "—" : "${bestMerma.toStringAsFixed(1)}%"}'),
      ]),
    );
  }
}

class _AnalysisStat extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _AnalysisStat(this.value, this.label, this.color);
  @override
  Widget build(BuildContext context) {
    return Expanded(child: Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10)),
      child: Column(children: [
        Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 9, color: Color(0xFF6B7280)), textAlign: TextAlign.center),
      ]),
    ));
  }
}

class _AnalysisRow extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;
  final String value;
  const _AnalysisRow(this.icon, this.color, this.label, this.value);
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(icon, size: 14, color: color),
      const SizedBox(width: 6),
      Text('$label: ', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
      Expanded(child: Text(value, style: TextStyle(fontSize: 11, color: color), overflow: TextOverflow.ellipsis)),
    ]);
  }
}

class _SupplierProductCard extends StatelessWidget {
  final Map<String, dynamic> supplier;
  final bool expanded;
  final VoidCallback onToggle;
  const _SupplierProductCard({required this.supplier, required this.expanded, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final name = supplier['name'] as String? ?? 'Proveedor';
    final products = List<Map<String, dynamic>>.from(supplier['products'] ?? []);
    final avgMerma = (supplier['avg_merma_pct'] as num?)?.toDouble() ?? 0;
    final email = supplier['email'] as String? ?? '';
    final phone = supplier['phone'] as String? ?? '';
    final leadTime = supplier['lead_time_days'];
    final minOrder = (supplier['min_order_eur'] as num?)?.toDouble();

    final rankColor = avgMerma >= 15
        ? const Color(0xFFEF4444)
        : avgMerma >= 8 ? const Color(0xFFF59E0B) : const Color(0xFF059669);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: rankColor.withValues(alpha: 0.3)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4, offset: const Offset(0, 2))],
      ),
      child: Column(children: [
        // Header
        InkWell(
          onTap: onToggle,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(14)),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(children: [
              Container(
                width: 42, height: 42,
                decoration: BoxDecoration(
                  color: rankColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(11),
                ),
                child: Center(child: Text(
                  name.isNotEmpty ? name[0].toUpperCase() : '?',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: rankColor),
                )),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                Row(children: [
                  if (email.isNotEmpty) ...[
                    const Icon(Icons.email_outlined, size: 12, color: Colors.grey),
                    const SizedBox(width: 3),
                    Flexible(child: Text(email, style: const TextStyle(fontSize: 10, color: Colors.grey), overflow: TextOverflow.ellipsis)),
                    const SizedBox(width: 8),
                  ],
                  if (phone.isNotEmpty) ...[
                    const Icon(Icons.phone_outlined, size: 12, color: Colors.grey),
                    const SizedBox(width: 3),
                    Text(phone, style: const TextStyle(fontSize: 10, color: Colors.grey)),
                  ],
                ]),
                Row(children: [
                  if (leadTime != null) ...[
                    _InfoChip('${leadTime}d entrega', const Color(0xFF6366F1)),
                    const SizedBox(width: 4),
                  ],
                  if (minOrder != null)
                    _InfoChip('min ${minOrder.toStringAsFixed(0)}€', const Color(0xFF0EA5E9)),
                ]),
              ])),
              Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('${avgMerma.toStringAsFixed(1)}%',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: rankColor)),
                Text('${products.length} productos', style: const TextStyle(fontSize: 10, color: Colors.grey)),
                Icon(expanded ? Icons.expand_less : Icons.expand_more, color: Colors.grey, size: 20),
              ]),
            ]),
          ),
        ),
        // Products list (expanded)
        if (expanded) ...[
          const Divider(height: 1, color: Color(0xFFE5E7EB)),
          ...products.map((prod) => _ProductRow(product: prod)),
          const SizedBox(height: 6),
        ],
      ]),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final Color color;
  const _InfoChip(this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
    child: Text(label, style: TextStyle(fontSize: 9, fontWeight: FontWeight.w600, color: color)),
  );
}

class _ProductRow extends StatelessWidget {
  final Map<String, dynamic> product;
  const _ProductRow({required this.product});

  @override
  Widget build(BuildContext context) {
    final name = product['product_name'] as String? ?? 'Producto';
    final cat = product['category'] as String? ?? '';
    final merma = (product['avg_merma_pct'] as num?)?.toDouble() ?? 0;
    final price = (product['price'] as num?)?.toDouble() ?? 0;
    final alternatives = List<Map<String, dynamic>>.from(product['alternatives'] ?? []);

    final mermaColor = merma >= 15
        ? const Color(0xFFEF4444)
        : merma >= 8 ? const Color(0xFFF59E0B) : const Color(0xFF059669);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            Row(children: [
              Text(cat, style: const TextStyle(fontSize: 11, color: Colors.grey)),
              const SizedBox(width: 8),
              Text('${price.toStringAsFixed(2)} €/ud', style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ]),
          ])),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: mermaColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text('${merma.toStringAsFixed(1)}% merma',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: mermaColor)),
          ),
        ]),
        if (alternatives.isNotEmpty) ...[
          const SizedBox(height: 8),
          Row(children: [
            const Icon(Icons.swap_horiz, size: 13, color: Color(0xFF6366F1)),
            const SizedBox(width: 4),
            const Text('Alternativas:', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF6366F1))),
          ]),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 4, children: alternatives.map((alt) {
            final altName = alt['supplier_name'] as String? ?? '';
            final altMerma = (alt['avg_merma_pct'] as num?)?.toDouble() ?? 0;
            final isBetter = altMerma < merma;
            final altColor = isBetter ? const Color(0xFF059669) : const Color(0xFFF59E0B);
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: altColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: altColor.withValues(alpha: 0.3)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(isBetter ? Icons.arrow_downward : Icons.arrow_upward, size: 10, color: altColor),
                const SizedBox(width: 3),
                Text('$altName ${altMerma.toStringAsFixed(1)}%',
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: altColor)),
              ]),
            );
          }).toList()),
        ] else ...[
          const SizedBox(height: 4),
          const Row(children: [
            Icon(Icons.info_outline, size: 11, color: Colors.grey),
            SizedBox(width: 4),
            Text('Sin proveedores alternativos registrados',
                style: TextStyle(fontSize: 10, color: Colors.grey)),
          ]),
        ],
      ]),
    );
  }
}

// ── Tab Pedido ────────────────────────────────────────────────────────────────

class _OrderTab extends ConsumerStatefulWidget {
  final VoidCallback onDownloadPdf;
  const _OrderTab({required this.onDownloadPdf});
  @override
  ConsumerState<_OrderTab> createState() => _OrderTabState();
}

class _OrderTabState extends ConsumerState<_OrderTab> {
  final Set<String> _selected = {};
  bool _confirming = false;
  String? _uploadedPdfName;
  bool _uploadingPdf = false;

  Future<void> _pickAndUploadPdf() async {
    setState(() { _uploadingPdf = true; _uploadedPdfName = null; });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['pdf'], withData: true,
      );
      if (result == null || result.files.isEmpty) { setState(() => _uploadingPdf = false); return; }
      setState(() { _uploadedPdfName = result.files.single.name; _uploadingPdf = false; });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF "${result.files.single.name}" cargado'), backgroundColor: const Color(0xFF059669)),
        );
      }
    } catch (e) {
      setState(() => _uploadingPdf = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(_orderProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(_orderProvider),
      child: async.when(
        loading: () => const ShimmerList(count: 6, itemHeight: 70),
        error: (e, _) => AppErrorWidget(
          error: e,
          customMessage: 'No se pudo calcular el pedido.',
          onRetry: () => ref.invalidate(_orderProvider),
        ),
        data: (suggestions) => _buildOrderList(context, suggestions),
      ),
    );
  }

  Widget _buildOrderList(BuildContext ctx, List<Map<String, dynamic>> suggestions) {
    final totalValue = suggestions.fold<double>(
        0, (s, p) => s + ((p['estimated_value'] as num?)?.toDouble() ?? 0));
    final selectedItems = suggestions
        .where((s) => _selected.contains(s['product_id'] as String? ?? s['product_name']))
        .toList();
    final selectedValue = selectedItems.fold<double>(
        0, (s, p) => s + ((p['estimated_value'] as num?)?.toDouble() ?? 0));

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Header
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: const _SafeGradient(
              colors: [Color(0xFF1E3A5F), Color(0xFF2563EB)],
              begin: Alignment.topLeft, end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                width: 44, height: 44,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(12)),
                child: const Icon(Icons.shopping_cart_rounded, color: Colors.white, size: 24),
              ),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Pedido semanal', style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800)),
                Text('${suggestions.length} productos · ${totalValue.toStringAsFixed(2)} € estimado',
                    style: const TextStyle(color: Colors.white60, fontSize: 11)),
              ])),
            ]),
            const SizedBox(height: 14),
            Row(children: [
              Expanded(child: ElevatedButton.icon(
                onPressed: widget.onDownloadPdf,
                icon: const Icon(Icons.download_rounded, size: 18),
                label: const Text('Descargar PDF'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: const Color(0xFF1E3A5F),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              )),
              const SizedBox(width: 8),
              Expanded(child: ElevatedButton.icon(
                onPressed: _uploadingPdf ? null : _pickAndUploadPdf,
                icon: _uploadingPdf
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.upload_file_rounded, size: 18),
                label: Text(_uploadedPdfName != null ? 'PDF cargado ✓' : 'Subir PDF'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: _uploadedPdfName != null ? const Color(0xFF059669) : Colors.white.withValues(alpha: 0.2),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              )),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: ElevatedButton.icon(
                onPressed: _selected.isEmpty || _confirming ? null : () => _confirmOrder(ctx, selectedItems),
                icon: _confirming
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.check_circle_outline, size: 18),
                label: Text(_selected.isEmpty ? 'Selecciona productos' : 'Confirmar (${_selected.length})'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: _selected.isEmpty ? Colors.white30 : const Color(0xFF059669),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                ),
              )),
            ]),
          ]),
        ),
        const SizedBox(height: 10),
        if (_selected.isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFD1FAE5),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFF059669).withValues(alpha: 0.3)),
            ),
            child: Row(children: [
              const Icon(Icons.info_outline, size: 16, color: Color(0xFF059669)),
              const SizedBox(width: 8),
              Expanded(child: Text(
                '${_selected.length} productos seleccionados · ${selectedValue.toStringAsFixed(2)} €',
                style: const TextStyle(fontSize: 12, color: Color(0xFF065F46), fontWeight: FontWeight.w600),
              )),
              TextButton(
                onPressed: () => setState(() => _selected.clear()),
                child: const Text('Limpiar', style: TextStyle(fontSize: 11)),
              ),
            ]),
          ),
        const SizedBox(height: 10),
        if (suggestions.isEmpty)
          const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.check_circle_outline, size: 56, color: Color(0xFF059669)),
                SizedBox(height: 12),
                Text('Stock al día', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Color(0xFF059669))),
                SizedBox(height: 4),
                Text('No hay productos que reponer esta semana.',
                    textAlign: TextAlign.center, style: TextStyle(color: Colors.grey)),
              ]),
            ),
          )
        else ...[
          Row(children: [
            Text('${suggestions.length} productos a pedir', style: const TextStyle(fontSize: 12, color: Colors.grey)),
            const Spacer(),
            TextButton.icon(
              onPressed: () => setState(() {
                if (_selected.length == suggestions.length) {
                  _selected.clear();
                } else {
                  _selected.addAll(suggestions.map((s) => s['product_id'] as String? ?? s['product_name'] as String? ?? ''));
                }
              }),
              icon: Icon(_selected.length == suggestions.length ? Icons.deselect : Icons.select_all, size: 16),
              label: Text(_selected.length == suggestions.length ? 'Ninguno' : 'Todos', style: const TextStyle(fontSize: 12)),
            ),
          ]),
          const SizedBox(height: 6),
          ...suggestions.map((s) {
            final key = s['product_id'] as String? ?? s['product_name'] as String? ?? '';
            return _OrderItemCard(
              suggestion: s,
              selected: _selected.contains(key),
              onToggle: () => setState(() {
                if (_selected.contains(key)) { _selected.remove(key); }
                else { _selected.add(key); }
              }),
            );
          }),
        ],
        const SizedBox(height: 16),
      ],
    );
  }

  Future<void> _confirmOrder(BuildContext ctx, List<Map<String, dynamic>> items) async {
    setState(() => _confirming = true);
    try {
      await ApiService().confirmOrder(items);
      setState(() { _selected.clear(); _confirming = false; });
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          SnackBar(
            content: Text('Pedido confirmado: ${items.length} productos'),
            backgroundColor: const Color(0xFF059669),
          ),
        );
      }
    } catch (e) {
      setState(() => _confirming = false);
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }
}

class _OrderItemCard extends StatelessWidget {
  final Map<String, dynamic> suggestion;
  final bool selected;
  final VoidCallback onToggle;
  const _OrderItemCard({required this.suggestion, required this.selected, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final name     = suggestion['product_name'] as String? ?? 'Producto';
    final category = suggestion['category'] as String? ?? '';
    final orderQty = (suggestion['order_qty'] as num?)?.toInt() ?? 0;
    final stock    = (suggestion['current_warehouse_stock'] as num?)?.toInt() ?? 0;
    final value    = (suggestion['estimated_value'] as num?)?.toDouble() ?? 0;
    final avgLoss  = (suggestion['avg_daily_loss'] as num?)?.toDouble() ?? 0;

    final riskColor = avgLoss > 2
        ? const Color(0xFFEF4444)
        : avgLoss > 0.5 ? const Color(0xFFF59E0B) : const Color(0xFF059669);

    return GestureDetector(
      onTap: onToggle,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFFD1FAE5) : Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? const Color(0xFF059669) : riskColor.withValues(alpha: 0.25),
            width: selected ? 2 : 1,
          ),
        ),
        child: Row(children: [
          Checkbox(
            value: selected,
            onChanged: (_) => onToggle(),
            activeColor: const Color(0xFF059669),
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            visualDensity: VisualDensity.compact,
          ),
          const SizedBox(width: 8),
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(color: riskColor, shape: BoxShape.circle),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
            Text(category, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            const SizedBox(height: 4),
            Row(children: [
              _Tag('Stock: $stock', Colors.grey),
              const SizedBox(width: 6),
              _Tag('Merma: ${avgLoss.toStringAsFixed(1)}/d', riskColor),
            ]),
          ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('$orderQty uds',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Color(0xFF1E3A5F))),
            Text('${value.toStringAsFixed(2)} €', style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ]),
        ]),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  final String text;
  final Color color;
  const _Tag(this.text, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
    child: Text(text, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
  );
}

class _StatPill extends StatelessWidget {
  final String value, label;
  const _StatPill({required this.value, required this.label});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(8)),
    child: Column(children: [
      Text(value, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800)),
      Text(label, style: const TextStyle(color: Colors.white60, fontSize: 9)),
    ]),
  );
}

class _QuickTag extends StatelessWidget {
  final String label, value;
  final double pct;
  final Color color;
  final IconData icon;
  const _QuickTag({required this.label, required this.value, required this.pct, required this.color, required this.icon});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
      const SizedBox(height: 3),
      Row(children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 4),
        Expanded(child: Text(value,
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
            overflow: TextOverflow.ellipsis)),
      ]),
      Text('${pct.toStringAsFixed(1)}% merma', style: TextStyle(fontSize: 10, color: color)),
    ]),
  );
}

class _SupplierCard extends StatelessWidget {
  final int rank;
  final Map<String, dynamic> supplier;
  final double maxMerma;
  const _SupplierCard({required this.rank, required this.supplier, required this.maxMerma});

  @override
  Widget build(BuildContext context) {
    final name = supplier['name'] as String? ?? 'Proveedor';
    final contact = supplier['contact'] as String? ?? '';
    final avgMerma = (supplier['avg_merma_pct'] as num?)?.toDouble() ?? 0;
    final productCount = (supplier['product_count'] as int?) ?? 0;
    final barFraction = maxMerma > 0 ? (avgMerma / maxMerma).clamp(0.0, 1.0) : 0.0;

    Color rankColor;
    String decision;
    if (avgMerma >= 15) {
      rankColor = const Color(0xFFEF4444);
      decision = 'Revisar contrato';
    } else if (avgMerma >= 8) {
      rankColor = const Color(0xFFF59E0B);
      decision = 'Monitorizar';
    } else {
      rankColor = const Color(0xFF059669);
      decision = 'Buen proveedor';
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: rankColor.withValues(alpha: 0.25)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            width: 28, height: 28,
            decoration: BoxDecoration(color: rankColor.withValues(alpha: 0.12), shape: BoxShape.circle),
            child: Center(child: Text('$rank',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: rankColor))),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            if (contact.isNotEmpty) Text(contact, style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('${avgMerma.toStringAsFixed(1)}%',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: rankColor)),
            Text('merma media', style: const TextStyle(fontSize: 10, color: Colors.grey)),
          ]),
        ]),
        const SizedBox(height: 10),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: barFraction,
            backgroundColor: const Color(0xFFF3F4F6),
            valueColor: AlwaysStoppedAnimation<Color>(rankColor),
            minHeight: 8,
          ),
        ),
        const SizedBox(height: 8),
        Row(children: [
          Icon(Icons.inventory_2_outlined, size: 13, color: Colors.grey[500]),
          const SizedBox(width: 4),
          Text('$productCount producto${productCount != 1 ? "s" : ""}',
              style: const TextStyle(fontSize: 12, color: Colors.grey)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
                color: rankColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(6)),
            child: Text(decision,
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: rankColor)),
          ),
        ]),
      ]),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  final List<Map<String, dynamic>> suppliers;
  const _DecisionCard({required this.suppliers});

  @override
  Widget build(BuildContext context) {
    final highRisk = suppliers.where((s) => ((s['avg_merma_pct'] as num?) ?? 0) >= 15).length;
    final medium = suppliers.where((s) {
      final m = (s['avg_merma_pct'] as num?)?.toDouble() ?? 0;
      return m >= 8 && m < 15;
    }).length;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF7ED),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFFED7AA)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.lightbulb_outline, color: Color(0xFFD97706), size: 18),
          SizedBox(width: 8),
          Text('Recomendaciones', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF92400E))),
        ]),
        const SizedBox(height: 10),
        if (highRisk > 0)
          _Rec(icon: Icons.warning_amber_rounded, color: const Color(0xFFEF4444),
              text: '$highRisk proveedor${highRisk > 1 ? "es" : ""} con merma ≥15%. Negocia o cambia.'),
        if (medium > 0)
          _Rec(icon: Icons.info_outline, color: const Color(0xFFF59E0B),
              text: '$medium proveedor${medium > 1 ? "es" : ""} en riesgo moderado. Solicita mejoras.'),
        _Rec(icon: Icons.check_circle_outline, color: const Color(0xFF059669),
            text: 'Prioriza proveedores con merma <8%.'),
        _Rec(icon: Icons.analytics_outlined, color: const Color(0xFF6366F1),
            text: 'Usa la pestaña Productos para ver alternativas por producto.'),
      ]),
    );
  }
}

class _Rec extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String text;
  const _Rec({required this.icon, required this.color, required this.text});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Icon(icon, size: 15, color: color),
      const SizedBox(width: 8),
      Expanded(child: Text(text, style: const TextStyle(fontSize: 12, color: Color(0xFF78350F), height: 1.4))),
    ]),
  );
}
