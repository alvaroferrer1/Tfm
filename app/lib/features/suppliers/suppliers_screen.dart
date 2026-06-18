import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/l10n.dart';
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
  return ApiService().getSupplierStats();
});

class SuppliersScreen extends ConsumerWidget {
  const SuppliersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_suppliersProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text('Proveedores'),
        actions: [
          TextButton(
            onPressed: () => ref.read(languageProvider.notifier).toggle(),
            child: Text(ref.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(_suppliersProvider),
          ),
        ],
      ),
      body: async.when(
        loading: () => const ShimmerList(count: 5, itemHeight: 88),
        error: (e, _) {
          debugPrint('[Proveedores] Error: $e');
          return AppErrorWidget(
            error: e,
            customMessage: 'No se pudieron cargar los proveedores. Comprueba la conexión con el servidor.',
            onRetry: () => ref.invalidate(_suppliersProvider),
          );
        },
        data: (suppliers) {
          if (suppliers.isEmpty) {
            return const Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.local_shipping_outlined, size: 56, color: Colors.grey),
                SizedBox(height: 12),
                Text('Sin datos de proveedores', style: TextStyle(fontSize: 16, color: Colors.grey)),
              ]),
            );
          }

          // Ordenar por merma media descendente
          final sorted = List<Map<String, dynamic>>.from(suppliers)
            ..sort((a, b) => ((b['avg_merma_pct'] as num?) ?? 0)
                .compareTo((a['avg_merma_pct'] as num?) ?? 0));

          final maxMerma = (sorted.first['avg_merma_pct'] as num?)?.toDouble() ?? 1.0;
          final totalProducts = sorted.fold<int>(
              0, (s, p) => s + ((p['product_count'] as int?) ?? 0));

          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(_suppliersProvider),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _SummaryCard(suppliers: sorted, totalProducts: totalProducts),
                const SizedBox(height: 16),
                Text('${sorted.length} proveedores · ordenados por % merma',
                    style: const TextStyle(fontSize: 12, color: Colors.grey)),
                const SizedBox(height: 12),
                ...sorted.asMap().entries.map((e) => _SupplierCard(
                      rank: e.key + 1,
                      supplier: e.value,
                      maxMerma: maxMerma,
                    )),
                const SizedBox(height: 16),
                _DecisionCard(suppliers: sorted),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final List<Map<String, dynamic>> suppliers;
  final int totalProducts;
  const _SummaryCard({required this.suppliers, required this.totalProducts});

  @override
  Widget build(BuildContext context) {
    final avgAll = suppliers.isEmpty
        ? 0.0
        : suppliers.fold<double>(
                0, (s, p) => s + ((p['avg_merma_pct'] as num?)?.toDouble() ?? 0)) /
            suppliers.length;
    final worst = suppliers.isNotEmpty ? suppliers.first : null;
    final best = suppliers.isNotEmpty ? suppliers.last : null;
    final highRisk = suppliers.where((s) => ((s['avg_merma_pct'] as num?) ?? 0) >= 15).length;

    return Column(
      children: [
        // Gradient hero header
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(18),
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
                  Text('${suppliers.length} proveedores · $totalProducts productos · merma media ${avgAll.toStringAsFixed(1)}%',
                      style: const TextStyle(color: Colors.white60, fontSize: 11)),
                ])),
              ]),
              const SizedBox(height: 16),
              Row(children: [
                _StatPill(value: '${suppliers.length}', label: 'proveedores'),
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
                      '$highRisk proveedor${highRisk > 1 ? "es" : ""} con merma ≥15% — revisar condiciones de contrato',
                      style: const TextStyle(color: Color(0xFFFCA5A5), fontSize: 11),
                    )),
                  ]),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        // Best/Worst quick comparison
        if (worst != null && best != null)
          Row(children: [
            Expanded(child: _QuickTag(
              label: 'Mayor merma',
              value: worst['name'] as String? ?? '',
              pct: (worst['avg_merma_pct'] as num?)?.toDouble() ?? 0,
              color: const Color(0xFFEF4444),
              icon: Icons.trending_up,
            )),
            const SizedBox(width: 10),
            Expanded(child: _QuickTag(
              label: 'Mejor índice',
              value: best['name'] as String? ?? '',
              pct: (best['avg_merma_pct'] as num?)?.toDouble() ?? 0,
              color: const Color(0xFF059669),
              icon: Icons.trending_down,
            )),
          ]),
      ],
    );
  }
}

class _StatPill extends StatelessWidget {
  final String value, label;
  const _StatPill({required this.value, required this.label});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(8),
    ),
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
        Expanded(child: Text(value, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color), overflow: TextOverflow.ellipsis)),
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
    final rows = (supplier['supplier_merma'] as List?) ?? [];
    final barFraction = maxMerma > 0 ? (avgMerma / maxMerma).clamp(0.0, 1.0) : 0.0;

    Color rankColor;
    String decision;
    if (avgMerma >= 15) {
      rankColor = const Color(0xFFEF4444);
      decision = 'Revisar contrato — merma alta';
    } else if (avgMerma >= 8) {
      rankColor = const Color(0xFFF59E0B);
      decision = 'Monitorizar — merma moderada';
    } else {
      rankColor = const Color(0xFF059669);
      decision = 'Buen proveedor — mantener';
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
            child: Center(child: Text('$rank', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: rankColor))),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            if (contact.isNotEmpty) Text(contact, style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('${avgMerma.toStringAsFixed(1)}%', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: rankColor)),
            Text('merma media', style: const TextStyle(fontSize: 10, color: Colors.grey)),
          ]),
        ]),
        const SizedBox(height: 10),
        // Barra de merma
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
          Text('$productCount producto${productCount != 1 ? 's' : ''}', style: const TextStyle(fontSize: 12, color: Colors.grey)),
          if (rows.isNotEmpty) ...[
            const SizedBox(width: 12),
            Icon(Icons.receipt_long_outlined, size: 13, color: Colors.grey[500]),
            const SizedBox(width: 4),
            Text('${rows.length} registros', style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ],
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: rankColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(6)),
            child: Text(decision, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: rankColor)),
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
          Text('Recomendaciones de compra', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF92400E))),
        ]),
        const SizedBox(height: 10),
        if (highRisk > 0)
          _Rec(icon: Icons.warning_amber_rounded, color: const Color(0xFFEF4444),
              text: '$highRisk proveedor${highRisk > 1 ? 'es' : ''} con merma alta (≥15%). Considera renegociar condiciones o cambiar de proveedor.'),
        if (medium > 0)
          _Rec(icon: Icons.info_outline, color: const Color(0xFFF59E0B),
              text: '$medium proveedor${medium > 1 ? 'es' : ''} en zona de riesgo moderado. Solicita mejoras de embalaje o plazos de entrega más cortos.'),
        _Rec(icon: Icons.check_circle_outline, color: const Color(0xFF059669),
            text: 'Prioriza pedidos a proveedores con merma <8% para reducir merma global.'),
        _Rec(icon: Icons.analytics_outlined, color: const Color(0xFF6366F1),
            text: 'Comparte estos datos con tu responsable de compras para negociar mejores condiciones.'),
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
