import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../core/supabase_client.dart';
import '../../core/theme.dart';

final _expiringBatchesProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final data = await supabase
      .from('batches')
      .select('*, products(*)')
      .eq('store_id', storeId)
      .eq('status', 'active')
      .lte(
        'expiry_date',
        DateTime.now().add(const Duration(days: 7)).toIso8601String().substring(0, 10),
      )
      .order('expiry_date');
  return List<Map<String, dynamic>>.from(data);
});

class MapScreen extends ConsumerStatefulWidget {
  /// Pasillo a abrir automáticamente (viene del deep link mermaops://map?pasillo=A).
  final String? initialPasillo;
  const MapScreen({super.key, this.initialPasillo});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  // Se consume una sola vez al llegar por deep link.
  String? _pendingPasillo;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _pendingPasillo = widget.initialPasillo;
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final batchesAsync = ref.watch(_expiringBatchesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pasillos urgentes'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(_expiringBatchesProvider),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(text: 'Mapa de pasillos'),
            Tab(text: 'Lista FEFO'),
          ],
        ),
      ),
      body: batchesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (batches) {
          // Deep link: abrir el pasillo correspondiente tras el primer frame.
          if (_pendingPasillo != null) {
            final pasillo = _pendingPasillo!;
            _pendingPasillo = null;
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!mounted) return;
              final items = _batchesForPasillo(batches, pasillo);
              if (items.isNotEmpty) {
                showPasilloDetail(context, pasillo, items);
              }
            });
          }
          return TabBarView(
            controller: _tabs,
            children: [
              _PasilloMap(batches: batches),
              _FefoList(batches: batches),
            ],
          );
        },
      ),
    );
  }
}

List<Map<String, dynamic>> _batchesForPasillo(
    List<Map<String, dynamic>> batches, String pasillo) {
  return batches.where((b) {
    final product = b['products'] as Map<String, dynamic>?;
    return (product?['pasillo'] as String? ?? '?') == pasillo;
  }).toList();
}

/// Función top-level reutilizable por el State y por _PasilloMap.
void showPasilloDetail(
    BuildContext context, String pasillo, List<Map<String, dynamic>> items) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.9,
      builder: (_, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.all(16),
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(
                color: Colors.grey[300],
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          Text(
            'Pasillo $pasillo — ${items.length} productos',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),
          ...items.map((b) {
            final product = b['products'] as Map<String, dynamic>?;
            final name = product?['name'] as String? ?? 'Producto';
            final est = product?['estanteria'] as String? ?? '?';
            final niv = product?['nivel'] as String? ?? '?';
            final expiry = b['expiry_date'] as String? ?? '';
            final qty = b['quantity'] as int? ?? 0;
            int days = 999;
            try {
              days = DateTime.parse(expiry).difference(DateTime.now()).inDays;
            } catch (_) {}

            return Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: UrgencyColors.forDays(days).withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                    color: UrgencyColors.forDays(days).withValues(alpha: 0.3)),
              ),
              child: Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: UrgencyColors.forDays(days),
                      shape: BoxShape.circle,
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
                          'E$est-N$niv | $qty uds | Caduca $expiry',
                          style:
                              const TextStyle(fontSize: 11, color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    ),
  );
}

class _PasilloMap extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  const _PasilloMap({required this.batches});

  Map<String, List<Map<String, dynamic>>> _groupByPasillo() {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final b in batches) {
      final product = b['products'] as Map<String, dynamic>?;
      final pasillo = product?['pasillo'] as String? ?? '?';
      map.putIfAbsent(pasillo, () => []).add(b);
    }
    return Map.fromEntries(
      map.entries.toList()..sort((a, b) => a.key.compareTo(b.key)),
    );
  }

  Color _pasilloColor(List<Map<String, dynamic>> items) {
    int minDays = 999;
    for (final b in items) {
      try {
        final d = DateTime.parse(b['expiry_date']).difference(DateTime.now()).inDays;
        if (d < minDays) minDays = d;
      } catch (_) {}
    }
    return UrgencyColors.forDays(minDays);
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _groupByPasillo();
    if (grouped.isEmpty) {
      return const Center(child: Text('Sin productos próximos a caducar'));
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final cols = constraints.maxWidth >= 600 ? 3 : 2;
        final spacing = 10.0;
        final cardWidth = (constraints.maxWidth - 32 - spacing * (cols - 1)) / cols;

        return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Toca un pasillo para ver el detalle',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: spacing,
            runSpacing: spacing,
            children: grouped.entries.map((entry) {
              final color = _pasilloColor(entry.value);
              final count = entry.value.length;
              return GestureDetector(
                onTap: () => showPasilloDetail(context, entry.key, entry.value),
                child: Container(
                  width: cardWidth,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: color.withValues(alpha: 0.4), width: 2),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(
                              color: color,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              'Pasillo ${entry.key}',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: color,
                              ),
                            ),
                          ),
                          GestureDetector(
                            onTap: () => _showQrDialog(context, entry.key),
                            child: Icon(
                              Icons.qr_code,
                              size: 20,
                              color: color.withValues(alpha: 0.7),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '$count producto${count != 1 ? 's' : ''}',
                        style: const TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),
          // Legend
          const Text('Leyenda:', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          _LegendItem(color: UrgencyColors.critical, label: 'Caduca hoy o mañana'),
          _LegendItem(color: UrgencyColors.high, label: 'Caduca en 2-3 días'),
          _LegendItem(color: UrgencyColors.medium, label: 'Caduca en 4-5 días'),
          _LegendItem(color: UrgencyColors.low, label: 'Caduca en 6-7 días'),
        ],
      ),
        );
      },
    );
  }

  void _showQrDialog(BuildContext context, String pasillo) {
    final deepLink = 'mermaops://map?pasillo=$pasillo';
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(
          'QR Pasillo $pasillo',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
          textAlign: TextAlign.center,
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE5E7EB)),
              ),
              child: QrImageView(
                data: deepLink,
                version: QrVersions.auto,
                size: 200,
                backgroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Escanea este QR en la entrada del pasillo para ver todos los productos próximos a caducar.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 4),
            Text(
              deepLink,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF)),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cerrar'),
          ),
        ],
      ),
    );
  }

}

class _LegendItem extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendItem({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(label, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _FefoList extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  const _FefoList({required this.batches});

  @override
  Widget build(BuildContext context) {
    if (batches.isEmpty) {
      return const Center(child: Text('Sin productos próximos a caducar'));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: batches.length,
      itemBuilder: (context, index) {
        final b = batches[index];
        final product = b['products'] as Map<String, dynamic>?;
        final name = product?['name'] as String? ?? 'Producto';
        final category = product?['category'] as String? ?? '';
        final pasillo = product?['pasillo'] as String? ?? '?';
        final expiry = b['expiry_date'] as String? ?? '';
        final qty = b['quantity'] as int? ?? 0;

        int days = 999;
        try {
          days = DateTime.parse(expiry).difference(DateTime.now()).inDays;
        } catch (_) {}

        final color = UrgencyColors.forDays(days);

        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(10),
            border: Border(left: BorderSide(color: color, width: 4)),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name,
                          style: const TextStyle(
                              fontWeight: FontWeight.w600, fontSize: 14)),
                      const SizedBox(height: 2),
                      Text(
                        'Pasillo $pasillo | $qty uds | $category',
                        style: const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      expiry,
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: color),
                    ),
                    Text(
                      days == 0
                          ? 'HOY'
                          : days < 0
                              ? 'CADUCADO'
                              : '$days días',
                      style: TextStyle(
                          fontSize: 11, color: color, fontWeight: FontWeight.w700),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
