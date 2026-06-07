import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../core/supabase_client.dart';
import '../../core/theme.dart';

// ── Data providers ─────────────────────────────────────────────────────────

// Supabase Realtime: el mapa se actualiza cuando llegan nuevas acciones críticas
// SupabaseStreamBuilder solo soporta un .eq() — filtramos 'pending' en cliente
final _liveActionsMapProvider = StreamProvider<List<Map<String, dynamic>>>((ref) {
  return supabase
      .from('actions')
      .stream(primaryKey: ['id'])
      .eq('store_id', storeId)
      .map((rows) => rows
          .cast<Map<String, dynamic>>()
          .where((a) => a['status'] == 'pending')
          .toList()
        ..sort((a, b) => ((b['priority_score'] as int? ?? 0)
            .compareTo(a['priority_score'] as int? ?? 0))));
});

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

// ── Helpers ─────────────────────────────────────────────────────────────────

int _daysLeft(String expiry) {
  try {
    return DateTime.parse(expiry).difference(DateTime.now()).inDays;
  } catch (_) {
    return 999;
  }
}

Color _urgencyColor(int days) => UrgencyColors.forDays(days);

String _urgencyLabel(int days) {
  if (days < 0) return 'CADUCADO';
  if (days == 0) return 'HOY';
  if (days == 1) return 'MAÑANA';
  return '$days días';
}

IconData _categoryIcon(String? category) {
  switch ((category ?? '').toLowerCase()) {
    case 'panadería':
    case 'panaderia':
      return Icons.breakfast_dining;
    case 'lácteos':
    case 'lacteos':
      return Icons.local_drink;
    case 'carnicería':
    case 'carniceria':
    case 'carne':
      return Icons.set_meal;
    case 'pescadería':
    case 'pescaderia':
    case 'pescado':
      return Icons.set_meal;
    case 'fruta':
    case 'frutas':
    case 'verdura':
    case 'verduras':
    case 'frutería':
    case 'fruteria':
      return Icons.eco;
    case 'congelados':
      return Icons.ac_unit;
    case 'bebidas':
      return Icons.local_bar;
    case 'conservas':
    case 'enlatados':
      return Icons.inventory_2;
    case 'charcutería':
    case 'charcuteria':
    case 'fiambres':
      return Icons.lunch_dining;
    default:
      return Icons.shopping_basket;
  }
}

// ── Main screen ──────────────────────────────────────────────────────────────

class MapScreen extends ConsumerStatefulWidget {
  final String? initialPasillo;
  const MapScreen({super.key, this.initialPasillo});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  String? _pendingPasillo;
  String? _selectedPasillo;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
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
    final liveActionsAsync = ref.watch(_liveActionsMapProvider);

    // Badge de críticos en tiempo real en el AppBar
    final criticalCount = liveActionsAsync.when(
      data: (actions) => actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length,
      loading: () => 0,
      error: (_, __) => 0,
    );

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: Row(mainAxisSize: MainAxisSize.min, children: [
          const Text('Mapa de tienda'),
          if (criticalCount > 0) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: const Color(0xFFEF4444),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text('$criticalCount CRÍTICO${criticalCount > 1 ? 'S' : ''}',
                  style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w800)),
            ),
          ],
        ]),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Actualizar',
            onPressed: () {
              ref.invalidate(_expiringBatchesProvider);
              setState(() => _selectedPasillo = null);
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(icon: Icon(Icons.map, size: 18), text: 'Plano'),
            Tab(icon: Icon(Icons.grid_view, size: 18), text: 'Pasillos'),
            Tab(icon: Icon(Icons.format_list_bulleted, size: 18), text: 'FEFO'),
          ],
        ),
      ),
      body: batchesAsync.when(
        loading: () => const ShimmerList(count: 4, itemHeight: 80),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              Text('No se pudo cargar el mapa', style: TextStyle(color: Colors.grey[600])),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => ref.invalidate(_expiringBatchesProvider),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
        data: (batches) {
          if (_pendingPasillo != null) {
            final pasillo = _pendingPasillo!;
            _pendingPasillo = null;
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!mounted) return;
              final items = _batchesForPasillo(batches, pasillo);
              if (items.isNotEmpty) _showPasilloDetail(context, pasillo, items);
            });
          }
          return Column(
            children: [
              _StoreHeader(batches: batches),
              Expanded(
                child: TabBarView(
                  controller: _tabs,
                  children: [
                    _StorePlan(
                      batches: batches,
                      selectedPasillo: _selectedPasillo,
                      onSelectPasillo: (p) {
                        setState(() => _selectedPasillo = p);
                        final items = _batchesForPasillo(batches, p);
                        _showPasilloDetail(context, p, items);
                      },
                    ),
                    _PasilloGrid(
                      batches: batches,
                      onSelectPasillo: (p) {
                        final items = _batchesForPasillo(batches, p);
                        _showPasilloDetail(context, p, items);
                      },
                    ),
                    _FefoList(batches: batches),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _showPasilloDetail(BuildContext context, String pasillo, List<Map<String, dynamic>> items) {
    showPasilloDetail(context, pasillo, items);
  }
}

List<Map<String, dynamic>> _batchesForPasillo(
    List<Map<String, dynamic>> batches, String pasillo) {
  return batches.where((b) {
    final product = b['products'] as Map<String, dynamic>?;
    return (product?['pasillo'] as String? ?? '?') == pasillo;
  }).toList();
}

// ── Store header summary ──────────────────────────────────────────────────────

class _StoreHeader extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  const _StoreHeader({required this.batches});

  @override
  Widget build(BuildContext context) {
    int critical = 0, high = 0, normal = 0;
    double valueAtRisk = 0;
    for (final b in batches) {
      final days = _daysLeft(b['expiry_date'] ?? '');
      final product = b['products'] as Map<String, dynamic>?;
      final qty = (b['quantity'] as int?) ?? 0;
      final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
      valueAtRisk += qty * price;
      if (days <= 1) {
        critical++;
      } else if (days <= 3) {
        high++;
      } else {
        normal++;
      }
    }
    final total = batches.length;
    final urgencyColor = critical > 0
        ? UrgencyColors.critical
        : high > 0
            ? UrgencyColors.high
            : UrgencyColors.low;

    return Container(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: urgencyColor.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 40,
            decoration: BoxDecoration(
              color: urgencyColor,
              borderRadius: BorderRadius.circular(5),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(storeName,
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                Text(
                  '$total prods · ${valueAtRisk.toStringAsFixed(0)} € en riesgo',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ],
            ),
          ),
          _KpiChip(label: 'HOY', value: critical.toString(), color: UrgencyColors.critical),
          const SizedBox(width: 6),
          _KpiChip(label: '2-3d', value: high.toString(), color: UrgencyColors.high),
          const SizedBox(width: 6),
          _KpiChip(label: '4-7d', value: normal.toString(), color: UrgencyColors.low),
        ],
      ),
    );
  }
}

class _KpiChip extends StatelessWidget {
  final String label, value;
  final Color color;
  const _KpiChip({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          Text(value,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 14, color: color)),
          Text(label, style: TextStyle(fontSize: 9, color: color)),
        ],
      ),
    );
  }
}

// ── Plano visual del supermercado ─────────────────────────────────────────────

class _StorePlan extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  final String? selectedPasillo;
  final void Function(String) onSelectPasillo;
  const _StorePlan({
    required this.batches,
    required this.selectedPasillo,
    required this.onSelectPasillo,
  });

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

  Color _pasilloUrgencyColor(List<Map<String, dynamic>> items) {
    int minDays = 999;
    for (final b in items) {
      final d = _daysLeft(b['expiry_date'] ?? '');
      if (d < minDays) minDays = d;
    }
    return _urgencyColor(minDays);
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _groupByPasillo();
    final pasillos = grouped.keys.toList()..sort();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          // Store floor plan
          Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFE5E7EB)),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.06),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              children: [
                // Store header bar
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                  decoration: const BoxDecoration(
                    color: Color(0xFF04503C),
                    borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.store, color: Colors.white, size: 16),
                      const SizedBox(width: 8),
                      Text(storeName.toUpperCase(),
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              fontSize: 14,
                              letterSpacing: 1.2)),
                      const Spacer(),
                      const Text('Plano interactivo',
                          style: TextStyle(color: Colors.white60, fontSize: 11)),
                    ],
                  ),
                ),
                // Perimeter fresh sections
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
                  child: Row(
                    children: [
                      _PerimeterSection(label: 'Frutas y\nVerduras', icon: Icons.eco, color: const Color(0xFF22C55E)),
                      const SizedBox(width: 8),
                      _PerimeterSection(label: 'Panadería\nFresca', icon: Icons.breakfast_dining, color: const Color(0xFFF59E0B)),
                      const SizedBox(width: 8),
                      _PerimeterSection(label: 'Carnicería\nPescadería', icon: Icons.set_meal, color: const Color(0xFFEF4444)),
                      const SizedBox(width: 8),
                      _PerimeterSection(label: 'Lácteos\nFríos', icon: Icons.local_drink, color: const Color(0xFF3B82F6)),
                    ],
                  ),
                ),
                // Aisle divider label
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Row(
                    children: [
                      const Expanded(child: Divider()),
                      const SizedBox(width: 8),
                      Text('PASILLOS INTERIORES',
                          style: TextStyle(fontSize: 10, color: Colors.grey[500], letterSpacing: 0.8)),
                      const SizedBox(width: 8),
                      const Expanded(child: Divider()),
                    ],
                  ),
                ),
                // Aisles grid
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: pasillos.isEmpty
                      ? Container(
                          height: 120,
                          alignment: Alignment.center,
                          child: const Text(
                            'Sin urgencias en los próximos 7 días',
                            style: TextStyle(color: Colors.grey, fontSize: 13),
                          ),
                        )
                      : _AisleGrid(
                          pasillos: pasillos,
                          grouped: grouped,
                          selectedPasillo: selectedPasillo,
                          pasilloColor: _pasilloUrgencyColor,
                          onSelectPasillo: onSelectPasillo,
                        ),
                ),
                // Checkout zone
                const SizedBox(height: 8),
                Container(
                  margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(4, (i) => Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 6),
                      child: Column(
                        children: [
                          const Icon(Icons.shopping_cart_checkout, size: 16, color: Colors.grey),
                          Text('Caja ${i + 1}',
                              style: const TextStyle(fontSize: 9, color: Colors.grey)),
                        ],
                      ),
                    )),
                  ),
                ),
                // Entrance
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  decoration: const BoxDecoration(
                    color: Color(0xFF04503C),
                    borderRadius: BorderRadius.vertical(bottom: Radius.circular(16)),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.sensor_door, color: Colors.white70, size: 16),
                      SizedBox(width: 6),
                      Text('ENTRADA / SALIDA',
                          style: TextStyle(
                              color: Colors.white70,
                              fontSize: 11,
                              letterSpacing: 1.0)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // Legend
          _Legend(),
          const SizedBox(height: 8),
          // Tap hint
          if (pasillos.isNotEmpty)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.touch_app, size: 14, color: Colors.grey[400]),
                const SizedBox(width: 4),
                Text(
                  'Toca un pasillo para ver el detalle y el QR',
                  style: TextStyle(fontSize: 11, color: Colors.grey[400]),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _PerimeterSection extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  const _PerimeterSection({required this.label, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(height: 4),
            Text(label,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 9, color: color, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _AisleGrid extends StatelessWidget {
  final List<String> pasillos;
  final Map<String, List<Map<String, dynamic>>> grouped;
  final String? selectedPasillo;
  final Color Function(List<Map<String, dynamic>>) pasilloColor;
  final void Function(String) onSelectPasillo;
  const _AisleGrid({
    required this.pasillos,
    required this.grouped,
    required this.selectedPasillo,
    required this.pasilloColor,
    required this.onSelectPasillo,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (ctx, constraints) {
        final cols = constraints.maxWidth >= 400 ? 3 : 2;
        final w = (constraints.maxWidth - 8.0 * (cols - 1)) / cols;
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: pasillos.map((pasillo) {
            final items = grouped[pasillo]!;
            final color = pasilloColor(items);
            final isSelected = pasillo == selectedPasillo;
            // Worst urgency in pasillo
            int minDays = 999;
            for (final b in items) {
              final d = _daysLeft(b['expiry_date'] ?? '');
              if (d < minDays) minDays = d;
            }

            return GestureDetector(
              onTap: () => onSelectPasillo(pasillo),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: w,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: isSelected ? color.withValues(alpha: 0.2) : color.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: color.withValues(alpha: isSelected ? 0.9 : 0.35),
                    width: isSelected ? 2.5 : 1.5,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 5),
                        Expanded(
                          child: Text(
                            'Pasillo $pasillo',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: color,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${items.length} prod.',
                      style: const TextStyle(fontSize: 10, color: Colors.grey),
                    ),
                    Text(
                      _urgencyLabel(minDays),
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: color,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        );
      },
    );
  }
}

class _Legend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _LegendItem(color: UrgencyColors.critical, label: 'Hoy/Mañana'),
          _LegendItem(color: UrgencyColors.high, label: '2-3 días'),
          _LegendItem(color: UrgencyColors.medium, label: '4-5 días'),
          _LegendItem(color: UrgencyColors.low, label: '6-7 días'),
        ],
      ),
    );
  }
}

// ── Pasillo grid tab ───────────────────────────────────────────────────────────

class _PasilloGrid extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  final void Function(String) onSelectPasillo;
  const _PasilloGrid({required this.batches, required this.onSelectPasillo});

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
      final d = _daysLeft(b['expiry_date'] ?? '');
      if (d < minDays) minDays = d;
    }
    return _urgencyColor(minDays);
  }

  double _valueAtRisk(List<Map<String, dynamic>> items) {
    double total = 0;
    for (final b in items) {
      final product = b['products'] as Map<String, dynamic>?;
      final qty = (b['quantity'] as int?) ?? 0;
      final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
      total += qty * price;
    }
    return total;
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _groupByPasillo();
    if (grouped.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.check_circle, size: 48, color: Color(0xFF22C55E)),
            SizedBox(height: 12),
            Text('Sin productos próximos a caducar',
                style: TextStyle(color: Colors.grey)),
            Text('¡Todo en orden esta semana!',
                style: TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
      );
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
              Text(
                '${grouped.length} pasillos con urgencias · Toca para ver el detalle',
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: spacing,
                runSpacing: spacing,
                children: grouped.entries.map((entry) {
                  final color = _pasilloColor(entry.value);
                  final count = entry.value.length;
                  final val = _valueAtRisk(entry.value);
                  // Worst days
                  int minDays = 999;
                  for (final b in entry.value) {
                    final d = _daysLeft(b['expiry_date'] ?? '');
                    if (d < minDays) minDays = d;
                  }
                  return GestureDetector(
                    onTap: () => onSelectPasillo(entry.key),
                    child: Container(
                      width: cardWidth,
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: color.withValues(alpha: 0.4), width: 2),
                        boxShadow: [
                          BoxShadow(
                            color: color.withValues(alpha: 0.12),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Container(
                                width: 14,
                                height: 14,
                                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
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
                                child: Icon(Icons.qr_code, size: 20,
                                    color: color.withValues(alpha: 0.7)),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '$count producto${count != 1 ? 's' : ''}',
                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                          ),
                          Text(
                            _urgencyLabel(minDays),
                            style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: color),
                          ),
                          if (val > 0)
                            Text(
                              '${val.toStringAsFixed(2)} € en riesgo',
                              style: const TextStyle(fontSize: 10, color: Colors.grey),
                            ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 24),
              _Legend(),
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
        title: Text('QR Pasillo $pasillo',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
            textAlign: TextAlign.center),
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
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
        ],
      ),
    );
  }
}

// ── Pasillo detail bottom sheet ───────────────────────────────────────────────

void showPasilloDetail(
    BuildContext context, String pasillo, List<Map<String, dynamic>> items) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.65,
      maxChildSize: 0.95,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: Color(0xFFF8FAFC),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            // Handle
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.grey[300],
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            // Header
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Pasillo $pasillo',
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                      ),
                      Text(
                        '${items.length} producto${items.length != 1 ? 's' : ''} con urgencia',
                        style: const TextStyle(fontSize: 13, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
                // Value at risk
                Builder(builder: (ctx) {
                  double val = 0;
                  for (final b in items) {
                    final product = b['products'] as Map<String, dynamic>?;
                    val += ((b['quantity'] as int?) ?? 0) *
                        ((product?['price'] as num?)?.toDouble() ?? 0.0);
                  }
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${val.toStringAsFixed(2)} €',
                      style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Color(0xFFD97706)),
                    ),
                  );
                }),
              ],
            ),
            const SizedBox(height: 16),
            // Products
            ...items.map((b) {
              final product = b['products'] as Map<String, dynamic>?;
              final name = product?['name'] as String? ?? 'Producto';
              final category = product?['category'] as String? ?? '';
              final est = product?['estanteria'] as String? ?? '?';
              final niv = product?['nivel'] as String? ?? '?';
              final expiry = b['expiry_date'] as String? ?? '';
              final qty = b['quantity'] as int? ?? 0;
              final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
              final days = _daysLeft(expiry);
              final color = _urgencyColor(days);
              final val = qty * price;

              return Container(
                margin: const EdgeInsets.only(bottom: 10),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border(left: BorderSide(color: color, width: 4)),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.04),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: color.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Icon(_categoryIcon(category), color: color, size: 20),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(name,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600, fontSize: 14)),
                            Text(
                              'E$est · N$niv  ·  $qty uds  ·  ${val.toStringAsFixed(2)} €',
                              style: const TextStyle(fontSize: 11, color: Colors.grey),
                            ),
                            if (category.isNotEmpty)
                              Text(category,
                                  style: const TextStyle(
                                      fontSize: 10, color: Colors.grey)),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(expiry,
                              style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: color)),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              _urgencyLabel(days),
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w800,
                                  color: color),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    ),
  );
}

// ── FEFO list ─────────────────────────────────────────────────────────────────

class _FefoList extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  const _FefoList({required this.batches});

  @override
  Widget build(BuildContext context) {
    if (batches.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.check_circle, size: 48, color: Color(0xFF22C55E)),
            SizedBox(height: 12),
            Text('Sin productos próximos a caducar',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: batches.length + 1,
      itemBuilder: (context, index) {
        if (index == 0) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              '${batches.length} productos · ordenados por caducidad (FEFO)',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          );
        }
        final b = batches[index - 1];
        final product = b['products'] as Map<String, dynamic>?;
        final name = product?['name'] as String? ?? 'Producto';
        final category = product?['category'] as String? ?? '';
        final pasillo = product?['pasillo'] as String? ?? '?';
        final expiry = b['expiry_date'] as String? ?? '';
        final qty = b['quantity'] as int? ?? 0;
        final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
        final days = _daysLeft(expiry);
        final color = _urgencyColor(days);
        final val = qty * price;

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
                Icon(_categoryIcon(category),
                    color: color.withValues(alpha: 0.7), size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name,
                          style: const TextStyle(
                              fontWeight: FontWeight.w600, fontSize: 14)),
                      Text(
                        'P.$pasillo  ·  $qty uds  ·  ${val.toStringAsFixed(2)} €',
                        style: const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                      if (category.isNotEmpty)
                        Text(category,
                            style: const TextStyle(
                                fontSize: 10, color: Colors.grey)),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(expiry,
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: color)),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(5),
                      ),
                      child: Text(
                        _urgencyLabel(days),
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w800,
                            color: color),
                      ),
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

// ── Shared widgets ────────────────────────────────────────────────────────────

class _LegendItem extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendItem({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 10, color: Colors.grey)),
      ],
    );
  }
}
