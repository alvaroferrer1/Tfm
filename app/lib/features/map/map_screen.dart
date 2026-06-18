import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../core/api_service.dart';
import '../../core/store_provider.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';
import '../../core/l10n.dart';
import '../../core/user_role_provider.dart';

// ── Data providers ─────────────────────────────────────────────────────────

final _liveActionsMapProvider = StreamProvider<List<Map<String, dynamic>>>((ref) {
  final sid = ref.watch(resolvedStoreIdProvider);
  return supabase
      .from('actions')
      .stream(primaryKey: ['id'])
      .eq('store_id', sid)
      .map((rows) => rows
          .cast<Map<String, dynamic>>()
          .where((a) => a['status'] == 'pending')
          .toList()
        ..sort((a, b) => ((b['priority_score'] as int? ?? 0)
            .compareTo(a['priority_score'] as int? ?? 0))));
});

final _expiringBatchesProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final sid = ref.watch(resolvedStoreIdProvider);
  final data = await supabase
      .from('batches')
      .select('*, products(*)')
      .eq('store_id', sid)
      .eq('status', 'active')
      .lte(
        'expiry_date',
        DateTime.now().add(const Duration(days: 7)).toIso8601String().substring(0, 10),
      )
      .order('expiry_date');
  return List<Map<String, dynamic>>.from(data);
});

final _allProductsCacheProvider = FutureProvider<Map<String, Map<String, dynamic>>>((ref) async {
  ref.watch(resolvedStoreIdProvider); // re-run when auth/store is ready
  try {
    final products = await api.getProducts();
    return {for (final p in products) p['id'] as String: p};
  } catch (_) {
    return {};
  }
});

// Pasillos derivados de la caché de productos (no query directa a Supabase)
final _storePassillosProvider = FutureProvider<List<String>>((ref) async {
  final cache = await ref.watch(_allProductsCacheProvider.future);
  if (cache.isEmpty) return ['1', '2', '3', '4', '5'];
  final pasillos = cache.values
      .map((p) => p['pasillo']?.toString() ?? '')
      .where((p) => p.isNotEmpty)
      .toSet()
      .toList()
    ..sort();
  return pasillos.isEmpty ? ['1', '2', '3', '4', '5'] : pasillos;
});

// ── Helpers ─────────────────────────────────────────────────────────────────

// Nombres reales de los pasillos del Super Martínez
const _pasilloNames = {
  '1': 'Panadería',
  '2': 'Lácteos',
  '3': 'Carnicería',
  '4': 'Pescadería',
  '5': 'Frutas y Verduras',
};

String _pasilloLabel(String? pasillo) {
  if (pasillo == null || pasillo == '?') return 'Sin ubicación';
  return _pasilloNames[pasillo] ?? 'Pasillo $pasillo';
}

// Enriquece un lote con datos de producto desde el caché si el join falló
Map<String, dynamic> _enrichBatch(
    Map<String, dynamic> b, Map<String, Map<String, dynamic>> cache) {
  if (b['products'] != null) return b;
  final pid = b['product_id'] as String?;
  if (pid != null && cache.containsKey(pid)) {
    return Map<String, dynamic>.from(b)..['products'] = cache[pid];
  }
  return b;
}

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
    // Caché de productos como respaldo cuando el join de Supabase falla por RLS
    final productsCache = ref.watch(_allProductsCacheProvider).valueOrNull ?? {};

    // Badge de críticos en tiempo real en el AppBar
    final criticalCount = liveActionsAsync.when(
      data: (actions) => actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length,
      loading: () => 0,
      error: (_, __) => 0,
    );

    final role = ref.watch(userRoleProvider).valueOrNull ?? UserRole.staff;
    final isManager = role.index >= UserRole.manager.index;
    final mapImageUrl = ref.watch(mapImageUrlProvider).valueOrNull;
    final storeDisplayName = ref.watch(resolvedStoreNameProvider);
    final pasillos = ref.watch(_storePassillosProvider).valueOrNull ?? ['1','2','3','4','5'];

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(storeDisplayName),
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
          TextButton(
            onPressed: () => ref.read(languageProvider.notifier).toggle(),
            child: Text(ref.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
          ),
          if (isManager)
            IconButton(
              icon: const Icon(Icons.upload_file_outlined),
              tooltip: 'Subir plano de tienda',
              onPressed: () => _uploadFloorPlan(context, ref),
            ),
          if (mapImageUrl != null)
            IconButton(
              icon: const Icon(Icons.map_outlined),
              tooltip: 'Ver plano subido',
              onPressed: () => _showFloorPlanImage(context, mapImageUrl),
            ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Actualizar',
            onPressed: () {
              ref.invalidate(_expiringBatchesProvider);
              ref.invalidate(_allProductsCacheProvider);
              ref.invalidate(_storePassillosProvider);
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
        data: (rawBatches) {
          // Enriquecer lotes con producto desde caché si el join devolvió null
          final batches = rawBatches
              .map((b) => _enrichBatch(b, productsCache))
              .toList();

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
                      pasillos: pasillos,
                      selectedPasillo: _selectedPasillo,
                      mapImageUrl: mapImageUrl,
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

  Future<void> _uploadFloorPlan(BuildContext context, WidgetRef ref) async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
    );
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.first;
    if (file.bytes == null) return;

    final sid = ref.read(resolvedStoreIdProvider);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Subiendo plano…'), duration: Duration(seconds: 2)),
    );
    try {
      final path = '$sid/floor-plan.${file.extension ?? 'jpg'}';
      // Eliminar versión anterior si existe, luego subir
      try { await supabase.storage.from('store-maps').remove([path]); } catch (_) {}
      await supabase.storage.from('store-maps').uploadBinary(path, file.bytes!);
      final url = supabase.storage.from('store-maps').getPublicUrl(path);
      await saveMapImageUrl(sid, url);
      ref.invalidate(mapImageUrlProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Plano subido correctamente'), backgroundColor: Color(0xFF059669)),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error subiendo plano: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  void _showFloorPlanImage(BuildContext context, String url) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        backgroundColor: Colors.transparent,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Image.network(url, fit: BoxFit.contain, errorBuilder: (_, __, ___) =>
              const Padding(padding: EdgeInsets.all(32), child: Text('No se pudo cargar la imagen', style: TextStyle(color: Colors.white)))),
          ),
          const SizedBox(height: 12),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cerrar', style: TextStyle(color: Colors.white)),
          ),
        ]),
      ),
    );
  }
}

List<Map<String, dynamic>> _batchesForPasillo(
    List<Map<String, dynamic>> batches, String pasillo) {
  return batches.where((b) {
    final product = b['products'] as Map<String, dynamic>?;
    final p = (product?['pasillo'] as String?)?.isNotEmpty == true
        ? product!['pasillo'] as String
        : 'Sin ubicación';
    return p == pasillo;
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
// Layout: plano real del Super Martínez. Cada sección = un pasillo con datos reales.
//
//  ┌──────────────────────────────────────────┐
//  │   ALMACÉN (banda superior)               │
//  ├──────────────┬───────────────────────────┤
//  │ P3 Carnicería│ P4 Pescadería             │
//  ├──────────────┼───────────────────────────┤
//  │ P1 Panadería │ P2 Lácteos               │
//  ├──────────────┴───────────────────────────┤
//  │      P5 Frutas y Verduras (perimetral)   │
//  ├──────────────────────────────────────────┤
//  │ 🛒 Caja 1 │ 🛒 Caja 2 │ 🛒 Caja 3     │
//  ├──────────────────────────────────────────┤
//  │          🚪 ENTRADA / SALIDA             │
//  └──────────────────────────────────────────┘

class _StorePlan extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  final List<String> pasillos;
  final String? selectedPasillo;
  final String? mapImageUrl;
  final void Function(String) onSelectPasillo;
  const _StorePlan({
    required this.batches,
    required this.pasillos,
    required this.selectedPasillo,
    required this.onSelectPasillo,
    this.mapImageUrl,
  });

  Map<String, List<Map<String, dynamic>>> _groupByPasillo() {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final b in batches) {
      final product = b['products'] as Map<String, dynamic>?;
      final p = (product?['pasillo'] as String?)?.isNotEmpty == true
          ? product!['pasillo'] as String
          : 'Sin ubicación';
      map.putIfAbsent(p, () => []).add(b);
    }
    return map;
  }

  int _minDays(List<Map<String, dynamic>> items) {
    int min = 999;
    for (final b in items) {
      final d = _daysLeft(b['expiry_date'] ?? '');
      if (d < min) min = d;
    }
    return min;
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _groupByPasillo();

    const tileIcons = {
      '1': Icons.breakfast_dining,
      '2': Icons.local_drink_outlined,
      '3': Icons.set_meal,
      '4': Icons.set_meal_outlined,
      '5': Icons.eco,
    };

    // Layout fijo de supermercado: fondo → frente
    const planRows = [
      ['3', '4'],  // Carnicería / Pescadería — zona fría al fondo
      ['1', '2'],  // Panadería / Lácteos — zona central
      ['5'],       // Frutas y Verduras — perimetral, junto a entrada
    ];

    Widget sectionTile(String pasillo) {
      final items = grouped[pasillo] ?? [];
      final minD = _minDays(items);
      final color = items.isEmpty ? const Color(0xFFCBD5E1) : _urgencyColor(minD);
      final isSelected = pasillo == selectedPasillo;

      return Expanded(
        child: GestureDetector(
          onTap: () => onSelectPasillo(pasillo),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            margin: const EdgeInsets.all(3),
            decoration: BoxDecoration(
              color: isSelected ? color.withValues(alpha: 0.22) : color.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: color.withValues(alpha: isSelected ? 1.0 : 0.55),
                width: isSelected ? 2.5 : 1.5,
              ),
              boxShadow: isSelected ? [BoxShadow(color: color.withValues(alpha: 0.3), blurRadius: 6, offset: const Offset(0, 2))] : null,
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(tileIcons[pasillo] ?? Icons.shopping_basket, color: color, size: 22),
                  const SizedBox(height: 6),
                  Text(
                    _pasilloLabel(pasillo),
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: color, height: 1.2),
                  ),
                  const SizedBox(height: 4),
                  if (items.isEmpty)
                    Text('Sin stock', style: TextStyle(fontSize: 9, color: Colors.grey[400]))
                  else ...[
                    Text('${items.length} prod.',
                        style: const TextStyle(fontSize: 9, color: Colors.grey)),
                    const SizedBox(height: 3),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(4)),
                      child: Text(_urgencyLabel(minD),
                          style: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.w700)),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    }

    // Build rows using fixed layout order, skip rows with no pasillos available
    List<Widget> buildPlanRows() {
      final rows = <Widget>[];
      for (final rowKeys in planRows) {
        final visible = rowKeys.where((p) => pasillos.contains(p)).toList();
        if (visible.isEmpty) continue;
        rows.add(Row(children: visible.map(sectionTile).toList()));
      }
      // Extra pasillos not in the fixed layout
      final extraPasillos = pasillos.where((p) => !['1','2','3','4','5'].contains(p)).toList();
      for (int i = 0; i < extraPasillos.length; i += 2) {
        if (i + 1 >= extraPasillos.length) {
          rows.add(Row(children: [sectionTile(extraPasillos[i])]));
        } else {
          rows.add(Row(children: [sectionTile(extraPasillos[i]), sectionTile(extraPasillos[i + 1])]));
        }
      }
      return rows;
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFFF8F9FA),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFD1D5DB), width: 1.5),
              boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 14, offset: const Offset(0, 4))],
            ),
            child: Column(
              children: [
                // Header — nombre tienda
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                  decoration: const BoxDecoration(
                    color: Color(0xFF065F46),
                    borderRadius: BorderRadius.vertical(top: Radius.circular(15)),
                  ),
                  child: Row(children: [
                    const Icon(Icons.store_rounded, color: Colors.white, size: 16),
                    const SizedBox(width: 8),
                    Text(storeName.toUpperCase(),
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 13, letterSpacing: 1.2)),
                    const Spacer(),
                    const Text('Toca un pasillo', style: TextStyle(color: Colors.white54, fontSize: 10)),
                  ]),
                ),
                // Almacén banner
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF374151),
                    border: Border(bottom: BorderSide(color: Colors.black.withValues(alpha: 0.15), width: 1)),
                  ),
                  child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Icon(Icons.warehouse_outlined, color: Colors.white54, size: 13),
                    SizedBox(width: 6),
                    Text('ALMACÉN / RECEPCIÓN', style: TextStyle(fontSize: 10, color: Colors.white54, letterSpacing: 1.0, fontWeight: FontWeight.w600)),
                  ]),
                ),
                // Plano subido por el encargado (si existe)
                if (mapImageUrl != null)
                  GestureDetector(
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (_) => Dialog(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              AppBar(
                                title: const Text('Plano de la tienda'),
                                automaticallyImplyLeading: false,
                                actions: [IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context))],
                              ),
                              Image.network(mapImageUrl!, fit: BoxFit.contain),
                            ],
                          ),
                        ),
                      );
                    },
                    child: Container(
                      width: double.infinity,
                      margin: const EdgeInsets.fromLTRB(8, 4, 8, 0),
                      height: 100,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFD1D5DB)),
                        image: DecorationImage(image: NetworkImage(mapImageUrl!), fit: BoxFit.cover),
                      ),
                      child: Align(
                        alignment: Alignment.bottomRight,
                        child: Container(
                          margin: const EdgeInsets.all(6),
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(6)),
                          child: const Text('Ver plano completo', style: TextStyle(color: Colors.white, fontSize: 10)),
                        ),
                      ),
                    ),
                  ),
                // Pasillos en layout fijo fondo→frente
                Padding(
                  padding: const EdgeInsets.fromLTRB(6, 8, 6, 4),
                  child: Column(children: buildPlanRows()),
                ),
                // Separador
                Container(
                  margin: const EdgeInsets.symmetric(horizontal: 8),
                  height: 1,
                  color: const Color(0xFFE5E7EB),
                ),
                // Cajas
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: List.generate(4, (i) => Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(color: const Color(0xFFE2E8F0), borderRadius: BorderRadius.circular(6)),
                          child: const Icon(Icons.shopping_cart_checkout, size: 16, color: Color(0xFF64748B)),
                        ),
                        const SizedBox(height: 2),
                        Text('Caja ${i + 1}', style: const TextStyle(fontSize: 9, color: Color(0xFF94A3B8), fontWeight: FontWeight.w600)),
                      ],
                    )),
                  ),
                ),
                // Entrada
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: const BoxDecoration(
                    color: Color(0xFF065F46),
                    borderRadius: BorderRadius.vertical(bottom: Radius.circular(15)),
                  ),
                  child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Icon(Icons.sensor_door_outlined, color: Colors.white, size: 18),
                    SizedBox(width: 8),
                    Text('ENTRADA / SALIDA', style: TextStyle(color: Colors.white, fontSize: 12, letterSpacing: 1.2, fontWeight: FontWeight.w700)),
                  ]),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _Legend(),
          const SizedBox(height: 8),
          // Resumen por pasillo — dinámico según la tienda
          ...pasillos.map((p) {
            final items = grouped[p] ?? [];
            if (items.isEmpty) return const SizedBox.shrink();
            final minD = _minDays(items);
            final color = _urgencyColor(minD);
            return GestureDetector(
              onTap: () => onSelectPasillo(p),
              child: Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: color.withValues(alpha: 0.3)),
                ),
                child: Row(children: [
                  Container(width: 4, height: 32, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
                  const SizedBox(width: 10),
                  Expanded(child: Text(_pasilloLabel(p), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600))),
                  Text('${items.length} prod.', style: const TextStyle(fontSize: 11, color: Colors.grey)),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
                    child: Text(_urgencyLabel(minD), style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(width: 6),
                  Icon(Icons.chevron_right, size: 16, color: Colors.grey[400]),
                ]),
              ),
            );
          }),
        ],
      ),
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
      final pasillo = (product?['pasillo'] as String?)?.isNotEmpty == true ? product!['pasillo'] as String : 'Sin ubicación';
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
                                  _pasilloLabel(entry.key),
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
        title: Text('QR — ${_pasilloLabel(pasillo)}',
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
                        _pasilloLabel(pasillo),
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
              final est = product?['estanteria'] as String?;
              final niv = product?['nivel'] as String?;
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
                              '${est != null ? 'E$est · ' : ''}${niv != null ? 'N$niv · ' : ''}$qty uds · ${val.toStringAsFixed(2)} €',
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
      itemCount: batches.length + 2,
      itemBuilder: (context, index) {
        if (index == 0) {
          return Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFBFDBFE)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.info_outline, color: Color(0xFF3B82F6), size: 18),
                const SizedBox(width: 8),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('¿Qué es FEFO?',
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1D4ED8))),
                      SizedBox(height: 3),
                      Text(
                        'First Expired, First Out — primero en caducar, primero en salir. '
                        'El sistema ordena los productos por fecha de caducidad para que el '
                        'empleado sepa exactamente qué colocar al frente del lineal hoy.',
                        style: TextStyle(fontSize: 12, color: Color(0xFF1E40AF), height: 1.4),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        }
        if (index == 1) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              '${batches.length} productos · ordenados por fecha de caducidad',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          );
        }
        final b = batches[index - 2];
        final product = b['products'] as Map<String, dynamic>?;
        final name = product?['name'] as String? ?? 'Producto';
        final category = product?['category'] as String? ?? '';
        final pasillo = (product?['pasillo'] as String?)?.isNotEmpty == true ? product!['pasillo'] as String : 'Sin ubicación';
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
