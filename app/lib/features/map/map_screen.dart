import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
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
  // Auto-refresh every 10 minutes so urgency colors stay current
  final t = Timer(const Duration(minutes: 10), ref.invalidateSelf);
  ref.onDispose(t.cancel);
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
    _tabs = TabController(length: 4, vsync: this);
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
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Actualizando...'), duration: Duration(seconds: 1)),
              );
              ref.invalidate(_expiringBatchesProvider);
              ref.invalidate(_warehouseQuickProvider);
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
            Tab(icon: Icon(Icons.warehouse_outlined, size: 18), text: 'Almacén'),
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
                    const _WarehouseQuickTab(),
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

// ── Floor plan helpers ─────────────────────────────────────────────────────────

Map<String, Rect> _floorPlanRects(Size size) {
  final w = size.width;
  final h = size.height;
  final mx = w * 0.04;
  final iw = w - mx * 2;
  final gap = iw * 0.025;
  final aw = (iw - gap * 3) / 4;
  return {
    'almacen': Rect.fromLTWH(mx, h * 0.015, iw, h * 0.145),
    '3': Rect.fromLTWH(mx,                      h * 0.18, aw, h * 0.33),
    '4': Rect.fromLTWH(mx + (aw + gap),          h * 0.18, aw, h * 0.33),
    '1': Rect.fromLTWH(mx + (aw + gap) * 2,      h * 0.18, aw, h * 0.33),
    '2': Rect.fromLTWH(mx + (aw + gap) * 3,      h * 0.18, aw, h * 0.33),
    '5': Rect.fromLTWH(mx, h * 0.535, iw, h * 0.10),
  };
}

// ── Store floor plan (StatefulWidget with CustomPainter) ───────────────────────

class _StorePlan extends ConsumerStatefulWidget {
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
  @override
  ConsumerState<_StorePlan> createState() => _StorePlanState();
}

class _StorePlanState extends ConsumerState<_StorePlan> {
  Size _cvsSize = Size.zero;

  Map<String, List<Map<String, dynamic>>> _grouped() {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final b in widget.batches) {
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

  void _onTap(Offset pos) {
    if (_cvsSize == Size.zero) return;
    final rects = _floorPlanRects(_cvsSize);
    for (final e in rects.entries) {
      if (e.value.contains(pos)) {
        if (e.key == 'almacen') { context.go('/warehouse'); return; }
        widget.onSelectPasillo(e.key);
        _showPasilloSheet(context, e.key, _grouped()[e.key] ?? []);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _grouped();
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          // Floor plan card
          Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFD1D5DB), width: 1.5),
              boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 14, offset: const Offset(0, 4))],
            ),
            child: Column(children: [
              // Header
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
                  const Text('Plano interactivo', style: TextStyle(color: Colors.white54, fontSize: 10)),
                ]),
              ),
              // Canvas
              LayoutBuilder(builder: (ctx, cons) {
                final cw = cons.maxWidth;
                final ch = cw * 1.42;
                return GestureDetector(
                  onTapUp: (d) {
                    _cvsSize = Size(cw, ch);
                    _onTap(d.localPosition);
                  },
                  child: SizedBox(
                    width: cw, height: ch,
                    child: RepaintBoundary(
                      child: CustomPaint(
                        painter: _SupermarketPainter(
                          batches: widget.batches,
                          selectedPasillo: widget.selectedPasillo,
                        ),
                        size: Size(cw, ch),
                      ),
                    ),
                  ),
                );
              }),
              // Optional uploaded plan
              if (widget.mapImageUrl != null)
                GestureDetector(
                  onTap: () => showDialog(
                    context: context,
                    builder: (_) => Dialog(child: Column(mainAxisSize: MainAxisSize.min, children: [
                      AppBar(title: const Text('Plano'), automaticallyImplyLeading: false,
                        actions: [IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context))]),
                      Image.network(widget.mapImageUrl!, fit: BoxFit.contain),
                    ])),
                  ),
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(12, 4, 12, 8),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0FDF4),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFF6EE7B7)),
                    ),
                    child: const Row(children: [
                      Icon(Icons.image_outlined, size: 16, color: Color(0xFF065F46)),
                      SizedBox(width: 8),
                      Text('Ver plano personalizado', style: TextStyle(fontSize: 12, color: Color(0xFF065F46), fontWeight: FontWeight.w600)),
                    ]),
                  ),
                ),
            ]),
          ),
          const SizedBox(height: 10),
          // Almacén shortcut card — datos reales de warehouse
          _InlineWarehouseCard(batches: widget.batches),
          const SizedBox(height: 10),
          _Legend(showMapAreas: true),
          const SizedBox(height: 8),
          ...widget.pasillos.map((p) {
            final items = grouped[p] ?? [];
            if (items.isEmpty) return const SizedBox.shrink();
            final minD = _minDays(items);
            final color = _urgencyColor(minD);
            return GestureDetector(
              onTap: () {
                widget.onSelectPasillo(p);
                _showPasilloSheet(context, p, items);
              },
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

  void _showPasilloSheet(BuildContext context, String pasillo, List<Map<String, dynamic>> items) {
    final pasilloName = _pasilloLabel(pasillo);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.55,
        minChildSize: 0.3,
        maxChildSize: 0.85,
        builder: (_, scrollCtrl) => Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(children: [
            Container(
              margin: const EdgeInsets.symmetric(vertical: 10),
              width: 40, height: 4,
              decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(2)),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(children: [
                Container(
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF065F46).withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.store_rounded, color: Color(0xFF065F46), size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(pasilloName, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: Color(0xFF065F46))),
                  Text('${items.length} producto${items.length != 1 ? 's' : ''} · Pasillo $pasillo',
                      style: const TextStyle(fontSize: 12, color: Colors.grey)),
                ])),
              ]),
            ),
            const Divider(height: 20),
            if (items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Column(children: [
                  Icon(Icons.check_circle_outline, color: Color(0xFF22C55E), size: 48),
                  SizedBox(height: 8),
                  Text('Pasillo sin alertas', style: TextStyle(fontWeight: FontWeight.w600, color: Color(0xFF22C55E))),
                  Text('Todo el stock esta en orden', style: TextStyle(color: Colors.grey, fontSize: 12)),
                ]),
              )
            else
              Expanded(
                child: ListView.builder(
                  controller: scrollCtrl,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: items.length,
                  itemBuilder: (_, i) {
                    final b = items[i];
                    final product = b['products'] as Map<String, dynamic>?;
                    final name = product?['name'] as String? ?? 'Producto';
                    final category = product?['category'] as String? ?? '';
                    final expiry = b['expiry_date'] as String? ?? '';
                    final qty = b['quantity'] as int? ?? 0;
                    final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
                    final days = _daysLeft(expiry);
                    final color = _urgencyColor(days);
                    final val = qty * price;
                    String badgeText;
                    if (days <= 0) { badgeText = 'HOY'; }
                    else if (days == 1) { badgeText = '1 DIA'; }
                    else { badgeText = '$days dias'; }
                    return Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.06),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: color.withValues(alpha: 0.3)),
                      ),
                      child: Row(children: [
                        Icon(_categoryIcon(category), color: color, size: 24),
                        const SizedBox(width: 12),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                          Text('$qty uds · ${val.toStringAsFixed(2)} EUR',
                              style: const TextStyle(fontSize: 12, color: Colors.grey)),
                        ])),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
                          child: Text(badgeText,
                              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 11)),
                        ),
                      ]),
                    );
                  },
                ),
              ),
          ]),
        ),
      ),
    );
  }
}

// ── Supermarket floor plan CustomPainter ───────────────────────────────────────

class _SupermarketPainter extends CustomPainter {
  final List<Map<String, dynamic>> batches;
  final String? selectedPasillo;

  _SupermarketPainter({required this.batches, this.selectedPasillo});

  @override
  bool shouldRepaint(_SupermarketPainter old) =>
      old.batches != batches || old.selectedPasillo != selectedPasillo;

  Map<String, List<Map<String, dynamic>>> _grouped() {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final b in batches) {
      final product = b['products'] as Map<String, dynamic>?;
      final p = (product?['pasillo'] as String?)?.isNotEmpty == true
          ? product!['pasillo'] as String
          : 'Sin ubicacion';
      map.putIfAbsent(p, () => []).add(b);
    }
    return map;
  }

  int _minD(List<Map<String, dynamic>> items) {
    int min = 999;
    for (final b in items) { final d = _daysLeft(b['expiry_date'] ?? ''); if (d < min) min = d; }
    return min;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final grouped = _grouped();
    final rects = _floorPlanRects(size);

    // Background floor
    canvas.drawRect(Rect.fromLTWH(0, 0, w, h), Paint()..color = const Color(0xFFF1F5F9));

    // Subtle grid
    final gp = Paint()..color = const Color(0xFFE2E8F0)..strokeWidth = 0.4;
    for (double x = 0; x < w; x += w * 0.1) { canvas.drawLine(Offset(x, 0), Offset(x, h), gp); }
    for (double y = 0; y < h; y += h * 0.05) { canvas.drawLine(Offset(0, y), Offset(w, y), gp); }

    // Outer building walls
    canvas.drawRRect(
      RRect.fromRectAndRadius(Rect.fromLTWH(w * 0.02, h * 0.008, w * 0.96, h * 0.84), const Radius.circular(4)),
      Paint()..color = const Color(0xFF1E293B)..style = PaintingStyle.stroke..strokeWidth = 2.5,
    );

    // Almacen divider wall
    canvas.drawLine(Offset(w * 0.02, h * 0.163), Offset(w * 0.98, h * 0.163),
      Paint()..color = const Color(0xFF475569)..strokeWidth = 1.5);
    // Door gap in divider wall
    canvas.drawLine(Offset(w * 0.46, h * 0.163), Offset(w * 0.54, h * 0.163),
      Paint()..color = const Color(0xFFF1F5F9)..strokeWidth = 5.0);
    // Door arc symbol
    final dp = Path()
      ..moveTo(w * 0.462, h * 0.163)
      ..arcToPoint(Offset(w * 0.538, h * 0.163),
          radius: Radius.circular(w * 0.038), clockwise: false);
    canvas.drawPath(dp, Paint()..color = const Color(0xFF94A3B8)..style = PaintingStyle.stroke..strokeWidth = 1.2);

    // ALMACEN zone
    _drawAlmacen(canvas, rects['almacen']!);

    // 4 vertical aisles
    for (final p in ['3', '4', '1', '2']) {
      final rect = rects[p]!;
      final items = grouped[p] ?? [];
      final color = items.isEmpty ? const Color(0xFFCBD5E1) : _urgencyColor(_minD(items));
      final urgency = items.isEmpty ? '' : _urgencyLabel(_minD(items));
      _drawAisle(canvas, rect, p, color, urgency, items.length, p == selectedPasillo);
    }

    // P5 wide aisle (Frutas y Verduras)
    {
      final rect = rects['5']!;
      final items = grouped['5'] ?? [];
      final color = items.isEmpty ? const Color(0xFFCBD5E1) : _urgencyColor(_minD(items));
      final urgency = items.isEmpty ? '' : _urgencyLabel(_minD(items));
      _drawWideAisle(canvas, rect, color, urgency, items.length, '5' == selectedPasillo);
    }

    // Checkout counters
    _drawCheckouts(canvas, size);

    // Entrance/exit
    _drawEntrance(canvas, size);
  }

  void _drawAlmacen(Canvas canvas, Rect rect) {
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(3)),
      Paint()..color = const Color(0xFF334155));

    canvas.save();
    canvas.clipRRect(RRect.fromRectAndRadius(rect, const Radius.circular(3)));

    // Diagonal hatching
    final hp = Paint()..color = const Color(0x18FFFFFF)..strokeWidth = 1.2;
    for (double x = rect.left - rect.height; x < rect.right; x += 10) {
      canvas.drawLine(Offset(x, rect.bottom), Offset(x + rect.height, rect.top), hp);
    }

    // Storage box rows
    final boxF = Paint()..color = const Color(0x35FFFFFF);
    final boxS = Paint()..color = const Color(0x55FFFFFF)..style = PaintingStyle.stroke..strokeWidth = 0.5;
    const bw = 13.0; const bh = 9.0; const bg = 3.0;
    final cols = ((rect.width - 20) / (bw + bg)).floor();
    for (int row = 0; row < 2; row++) {
      for (int col = 0; col < cols; col++) {
        final br = Rect.fromLTWH(rect.left + 10 + col * (bw + bg), rect.bottom - 14 - row * (bh + 2), bw, bh);
        canvas.drawRect(br, boxF);
        canvas.drawRect(br, boxS);
      }
    }

    _txt(canvas, 'ALMACEN', Offset(rect.center.dx, rect.center.dy - 6),
      const TextStyle(color: Color(0xFFE2E8F0), fontSize: 11, fontWeight: FontWeight.w800,
        letterSpacing: 2.5, decoration: TextDecoration.none), maxW: rect.width - 8);
    _txt(canvas, 'Toca para ver inventario',
      Offset(rect.center.dx, rect.center.dy + 9),
      TextStyle(color: Colors.white.withValues(alpha: 0.45), fontSize: 7.5, decoration: TextDecoration.none),
      maxW: rect.width - 8);

    canvas.restore();
  }

  void _drawAisle(Canvas canvas, Rect rect, String p, Color color, String urgency, int count, bool sel) {
    // Fill
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)),
      Paint()..color = sel ? color.withValues(alpha: 0.18) : color.withValues(alpha: 0.07));

    // Left shelf unit
    _drawShelf(canvas, Rect.fromLTWH(rect.left + 3, rect.top + 26, rect.width * 0.30, rect.height - 30), color);
    // Right shelf unit
    _drawShelf(canvas, Rect.fromLTWH(rect.right - 3 - rect.width * 0.30, rect.top + 26, rect.width * 0.30, rect.height - 30), color);

    // Center walkway
    canvas.drawRect(
      Rect.fromLTWH(rect.left + rect.width * 0.33, rect.top + 26, rect.width * 0.34, rect.height - 30),
      Paint()..color = const Color(0xFFF8FAFC).withValues(alpha: 0.7));

    // Header strip
    final hdr = Rect.fromLTWH(rect.left, rect.top, rect.width, 24);
    canvas.drawRRect(RRect.fromRectAndRadius(hdr, const Radius.circular(4)),
      Paint()..color = color.withValues(alpha: sel ? 0.85 : 0.65));
    _txt(canvas, _aisleLabel(p), Offset(rect.center.dx, rect.top + 12),
      const TextStyle(color: Colors.white, fontSize: 8, fontWeight: FontWeight.w800,
        letterSpacing: 0.3, decoration: TextDecoration.none), maxW: rect.width - 4);

    if (count > 0) {
      _txt(canvas, '$count prod.', Offset(rect.center.dx, rect.top + 32),
        TextStyle(color: color, fontSize: 7, fontWeight: FontWeight.w600, decoration: TextDecoration.none),
        maxW: rect.width - 4);

      final bw = rect.width * 0.80;
      final br = Rect.fromCenter(center: Offset(rect.center.dx, rect.bottom - 12), width: bw, height: 13);
      canvas.drawRRect(RRect.fromRectAndRadius(br, const Radius.circular(3)), Paint()..color = color);
      _txt(canvas, urgency, br.center,
        const TextStyle(color: Colors.white, fontSize: 7, fontWeight: FontWeight.w800,
          letterSpacing: 0.3, decoration: TextDecoration.none), maxW: bw - 2);
    }

    // Border
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)),
      Paint()..color = color.withValues(alpha: sel ? 1.0 : 0.45)
        ..style = PaintingStyle.stroke..strokeWidth = sel ? 2.5 : 1.5);
  }

  void _drawShelf(Canvas canvas, Rect r, Color color) {
    canvas.drawRect(r, Paint()..color = color.withValues(alpha: 0.07));
    final sp = Paint()..color = color.withValues(alpha: 0.30)..strokeWidth = 1.5;
    const ns = 5;
    final gap = r.height / (ns + 1);
    for (int i = 1; i <= ns; i++) {
      final sy = r.top + gap * i;
      canvas.drawLine(Offset(r.left + 1, sy), Offset(r.right - 1, sy), sp);
      // Product boxes on shelf
      const pw = 3.5; const phMax = 5.0; const pg = 1.5;
      final nc = ((r.width - 2) / (pw + pg)).floor();
      for (int j = 0; j < nc; j++) {
        final px = r.left + 1 + j * (pw + pg);
        final ph = phMax * (0.5 + (j % 3) * 0.25);
        canvas.drawRect(Rect.fromLTWH(px, sy - ph, pw, ph),
          Paint()..color = color.withValues(alpha: 0.22));
      }
    }
  }

  void _drawWideAisle(Canvas canvas, Rect rect, Color color, String urgency, int count, bool sel) {
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)),
      Paint()..color = sel ? color.withValues(alpha: 0.18) : color.withValues(alpha: 0.07));

    // Display stand dividers
    final dp = Paint()..color = color.withValues(alpha: 0.25)..strokeWidth = 1.5;
    for (int i = 1; i < 8; i++) {
      final x = rect.left + rect.width * i / 8;
      canvas.drawLine(Offset(x, rect.top + 3), Offset(x, rect.bottom - 3), dp);
    }

    _txt(canvas, 'FRUTAS Y VERDURAS',
      Offset(rect.left + rect.width * 0.35, rect.center.dy),
      TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w800,
        letterSpacing: 0.5, decoration: TextDecoration.none), maxW: rect.width * 0.55);

    if (count > 0) {
      _txt(canvas, '$count prod.',
        Offset(rect.left + rect.width * 0.35, rect.center.dy + 13),
        TextStyle(color: color.withValues(alpha: 0.8), fontSize: 7.5,
          fontWeight: FontWeight.w500, decoration: TextDecoration.none));
      final br = Rect.fromCenter(center: Offset(rect.right - 36, rect.center.dy), width: 56, height: 14);
      canvas.drawRRect(RRect.fromRectAndRadius(br, const Radius.circular(3)), Paint()..color = color);
      _txt(canvas, urgency, br.center,
        const TextStyle(color: Colors.white, fontSize: 7.5, fontWeight: FontWeight.w800, decoration: TextDecoration.none));
    }

    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)),
      Paint()..color = color.withValues(alpha: sel ? 1.0 : 0.45)
        ..style = PaintingStyle.stroke..strokeWidth = sel ? 2.5 : 1.5);
  }

  void _drawCheckouts(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final mx = w * 0.04;
    final iw = w - mx * 2;
    const n = 4; const gap = 6.0;
    final cw = (iw - gap * (n - 1)) / n;
    final ct = h * 0.660;
    final ch = h * 0.072;

    for (int i = 0; i < n; i++) {
      final cx = mx + i * (cw + gap);
      final cr = Rect.fromLTWH(cx, ct, cw, ch);
      canvas.drawRRect(RRect.fromRectAndRadius(cr, const Radius.circular(3)),
        Paint()..color = const Color(0xFFE2E8F0));
      canvas.drawRRect(RRect.fromRectAndRadius(cr, const Radius.circular(3)),
        Paint()..color = const Color(0xFF94A3B8)..style = PaintingStyle.stroke..strokeWidth = 0.8);
      // Belt
      canvas.drawRRect(RRect.fromRectAndRadius(
          Rect.fromLTWH(cx + 3, ct + ch * 0.35, cw - 6, ch * 0.25), const Radius.circular(2)),
        Paint()..color = const Color(0xFF64748B));
      // Screen
      canvas.drawRRect(RRect.fromRectAndRadius(
          Rect.fromLTWH(cx + 2, ct + 2, cw * 0.35, ch * 0.30), const Radius.circular(2)),
        Paint()..color = const Color(0xFF93C5FD));
      _txt(canvas, 'CAJA ${i + 1}', Offset(cx + cw / 2, ct + ch * 0.82),
        const TextStyle(color: Color(0xFF64748B), fontSize: 6.5, fontWeight: FontWeight.w700,
          letterSpacing: 0.5, decoration: TextDecoration.none));
    }
  }

  void _drawEntrance(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final er = Rect.fromLTWH(w * 0.02, h * 0.742, w * 0.96, h * 0.058);
    canvas.drawRRect(RRect.fromRectAndRadius(er, const Radius.circular(4)),
      Paint()..color = const Color(0xFF065F46));
    // Sliding door gaps
    canvas.drawRect(Rect.fromLTWH(w * 0.36, er.top + 1, w * 0.11, er.height - 2),
      Paint()..color = const Color(0xFF047857));
    canvas.drawRect(Rect.fromLTWH(w * 0.53, er.top + 1, w * 0.11, er.height - 2),
      Paint()..color = const Color(0xFF047857));
    _txt(canvas, 'ENTRADA / SALIDA', er.center,
      const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800,
        letterSpacing: 2.0, decoration: TextDecoration.none));
  }

  void _txt(Canvas canvas, String text, Offset center, TextStyle style, {double maxW = 300}) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
      textAlign: TextAlign.center,
    )..layout(maxWidth: maxW);
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  String _aisleLabel(String p) {
    const labels = {'1': 'PANADERIA', '2': 'LACTEOS', '3': 'CARNICERIA', '4': 'PESCADERIA', '5': 'FRUTAS'};
    return labels[p] ?? 'P$p';
  }
}

class _Legend extends StatelessWidget {
  final bool showMapAreas;
  const _Legend({this.showMapAreas = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Urgencia por caducidad',
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Color(0xFF374151), letterSpacing: 0.5)),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _LegendItem(color: UrgencyColors.critical, label: 'Hoy/Mañana'),
              _LegendItem(color: UrgencyColors.high, label: '2-3 días'),
              _LegendItem(color: UrgencyColors.medium, label: '4-5 días'),
              _LegendItem(color: UrgencyColors.low, label: '6-7 días'),
            ],
          ),
          if (showMapAreas) ...[
            const SizedBox(height: 10),
            const Divider(height: 1, color: Color(0xFFF3F4F6)),
            const SizedBox(height: 10),
            const Text('Zonas del plano',
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Color(0xFF374151), letterSpacing: 0.5)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 14,
              runSpacing: 6,
              children: [
                _MapAreaItem(color: const Color(0xFF334155), label: 'Almacén (arriba)'),
                _MapAreaItem(color: const Color(0xFF6B7280), label: 'Pasillos (toca)'),
                _MapAreaItem(color: const Color(0xFFE2E8F0), label: 'Cajas de cobro'),
                _MapAreaItem(color: const Color(0xFF065F46), label: 'Entrada/Salida'),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _MapAreaItem extends StatelessWidget {
  final Color color;
  final String label;
  const _MapAreaItem({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
        width: 16, height: 10,
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2)),
      ),
      const SizedBox(width: 5),
      Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF6B7280))),
    ]);
  }
}

// ── Pasillo route tab (aisle pick list, expandable) ───────────────────────────

class _PasilloGrid extends StatefulWidget {
  final List<Map<String, dynamic>> batches;
  final void Function(String) onSelectPasillo;
  const _PasilloGrid({required this.batches, required this.onSelectPasillo});

  @override
  State<_PasilloGrid> createState() => _PasilloGridState();
}

class _PasilloGridState extends State<_PasilloGrid> {
  final Set<String> _expanded = {'1', '2', '3', '4', '5'};

  Map<String, List<Map<String, dynamic>>> _groupByPasillo() {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final b in widget.batches) {
      final product = b['products'] as Map<String, dynamic>?;
      final pasillo = (product?['pasillo'] as String?)?.isNotEmpty == true
          ? product!['pasillo'] as String
          : 'Sin ubicación';
      map.putIfAbsent(pasillo, () => []).add(b);
    }
    return Map.fromEntries(map.entries.toList()..sort((a, b) => a.key.compareTo(b.key)));
  }

  int _minDaysGroup(List<Map<String, dynamic>> items) {
    int min = 999;
    for (final b in items) {
      final d = _daysLeft(b['expiry_date'] ?? '');
      if (d < min) min = d;
    }
    return min;
  }

  double _valueAtRisk(List<Map<String, dynamic>> items) {
    double total = 0;
    for (final b in items) {
      final product = b['products'] as Map<String, dynamic>?;
      total += ((b['quantity'] as int?) ?? 0) * ((product?['price'] as num?)?.toDouble() ?? 0.0);
    }
    return total;
  }

  @override
  Widget build(BuildContext context) {
    final grouped = _groupByPasillo();
    if (grouped.isEmpty) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: const [
          Icon(Icons.check_circle, size: 48, color: Color(0xFF22C55E)),
          SizedBox(height: 12),
          Text('Sin productos próximos a caducar', style: TextStyle(color: Colors.grey)),
          Text('¡Todo en orden esta semana!', style: TextStyle(fontSize: 12, color: Colors.grey)),
        ]),
      );
    }

    // Sort by urgency (most critical first)
    final sortedEntries = grouped.entries.toList()
      ..sort((a, b) => _minDaysGroup(a.value).compareTo(_minDaysGroup(b.value)));

    final totalItems = widget.batches.length;
    final criticalCount = widget.batches
        .where((b) => _daysLeft(b['expiry_date'] ?? '') <= 1)
        .length;
    final totalVal = widget.batches.fold(0.0, (sum, b) {
      final p = b['products'] as Map<String, dynamic>?;
      return sum + ((b['quantity'] as int?) ?? 0) * ((p?['price'] as num?)?.toDouble() ?? 0.0);
    });

    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
      children: [
        // Route summary header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF065F46), Color(0xFF047857)],
              begin: Alignment.topLeft, end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(children: [
            const Icon(Icons.route, color: Colors.white, size: 22),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Ruta de reposición',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 15)),
              Text(
                '$totalItems productos · ${totalVal.toStringAsFixed(0)} € en riesgo'
                '${criticalCount > 0 ? ' · $criticalCount críticos' : ''}',
                style: const TextStyle(color: Colors.white70, fontSize: 11),
              ),
            ])),
            Column(children: [
              Text('${sortedEntries.length}',
                  style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w900, height: 1)),
              const Text('pasillos', style: TextStyle(color: Colors.white60, fontSize: 9)),
            ]),
          ]),
        ),
        const SizedBox(height: 8),
        const Text(
          'Ordenado por urgencia · Toca el encabezado para expandir/colapsar',
          style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF), fontStyle: FontStyle.italic),
        ),
        const SizedBox(height: 8),
        ...sortedEntries.asMap().entries.map((e) {
          final stepNum = e.key + 1;
          final pasillo = e.value.key;
          final items = e.value.value;
          final minD = _minDaysGroup(items);
          final color = _urgencyColor(minD);
          final val = _valueAtRisk(items);
          final isExpanded = _expanded.contains(pasillo);

          // Sort items within aisle by expiry (most urgent first)
          final sortedItems = List<Map<String, dynamic>>.from(items)
            ..sort((a, b) =>
                _daysLeft(a['expiry_date'] ?? '').compareTo(_daysLeft(b['expiry_date'] ?? '')));

          return Container(
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color.withValues(alpha: isExpanded ? 0.4 : 0.2)),
              boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 6, offset: const Offset(0, 2))],
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Header row
              InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => setState(() {
                  if (isExpanded) {
                    _expanded.remove(pasillo);
                  } else {
                    _expanded.add(pasillo);
                  }
                }),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(children: [
                    Container(
                      width: 30, height: 30,
                      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(15)),
                      child: Center(child: Text('$stepNum',
                          style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w800))),
                    ),
                    const SizedBox(width: 10),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_pasilloLabel(pasillo),
                          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: color)),
                      Text('${items.length} producto${items.length != 1 ? 's' : ''} · ${val.toStringAsFixed(2)} €',
                          style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
                    ])),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
                      child: Text(_urgencyLabel(minD),
                          style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
                    ),
                    const SizedBox(width: 4),
                    InkWell(
                      onTap: () => _showQrDialog(context, pasillo),
                      borderRadius: BorderRadius.circular(8),
                      child: Padding(
                        padding: const EdgeInsets.all(6),
                        child: Icon(Icons.qr_code_2, size: 18, color: color.withValues(alpha: 0.65)),
                      ),
                    ),
                    Icon(
                      isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                      size: 20, color: const Color(0xFF9CA3AF),
                    ),
                  ]),
                ),
              ),
              // Expanded product list
              if (isExpanded) ...[
                const Divider(height: 1, color: Color(0xFFF3F4F6)),
                ...sortedItems.map((b) {
                  final product = b['products'] as Map<String, dynamic>?;
                  final name = product?['name'] as String? ?? 'Producto';
                  final cat = product?['category'] as String? ?? '';
                  final est = product?['estanteria'] as String?;
                  final niv = product?['nivel'] as String?;
                  final qty = b['quantity'] as int? ?? 0;
                  final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
                  final expiry = b['expiry_date'] as String? ?? '';
                  final days = _daysLeft(expiry);
                  final bColor = _urgencyColor(days);
                  final itemVal = qty * price;

                  final locParts = <String>[];
                  if (est != null && est.isNotEmpty) locParts.add('Estante $est');
                  if (niv != null && niv.isNotEmpty) locParts.add('Nivel $niv');

                  return Container(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                    decoration: BoxDecoration(
                      color: bColor.withValues(alpha: 0.03),
                      border: Border(
                        top: const BorderSide(color: Color(0xFFF3F4F6)),
                        left: BorderSide(color: bColor, width: 3),
                      ),
                    ),
                    child: Row(children: [
                      Icon(_categoryIcon(cat), size: 20, color: bColor),
                      const SizedBox(width: 10),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 2),
                        Row(children: [
                          if (locParts.isNotEmpty) ...[
                            Icon(Icons.location_on_outlined, size: 11, color: const Color(0xFF9CA3AF)),
                            const SizedBox(width: 2),
                            Text(locParts.join(' · '),
                                style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
                            const SizedBox(width: 8),
                          ],
                          Text('$qty uds', style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
                          const SizedBox(width: 6),
                          Text('${itemVal.toStringAsFixed(2)} €',
                              style: const TextStyle(fontSize: 11, color: Color(0xFF059669), fontWeight: FontWeight.w600)),
                        ]),
                      ])),
                      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                          decoration: BoxDecoration(color: bColor, borderRadius: BorderRadius.circular(6)),
                          child: Text(_urgencyLabel(days),
                              style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w800)),
                        ),
                        const SizedBox(height: 2),
                        Text(expiry, style: const TextStyle(fontSize: 9, color: Color(0xFF9CA3AF))),
                      ]),
                    ]),
                  );
                }),
                // See full detail button
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 6, 12, 10),
                  child: GestureDetector(
                    onTap: () => widget.onSelectPasillo(pasillo),
                    child: Row(children: [
                      Icon(Icons.open_in_full, size: 12, color: color.withValues(alpha: 0.7)),
                      const SizedBox(width: 6),
                      Text('Ver ficha completa del pasillo',
                          style: TextStyle(fontSize: 11, color: color.withValues(alpha: 0.8), fontWeight: FontWeight.w600)),
                    ]),
                  ),
                ),
              ],
            ]),
          );
        }),
        const SizedBox(height: 8),
        _Legend(),
      ],
    );
  }

  void _showQrDialog(BuildContext context, String pasillo) {
    final deepLink = 'mermaops://map?pasillo=$pasillo';
    showDialog(
      context: context,
      builder: (dlgCtx) => AlertDialog(
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
          TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('Cerrar')),
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

// ── FEFO list mejorado ────────────────────────────────────────────────────────

class _FefoList extends StatefulWidget {
  final List<Map<String, dynamic>> batches;
  const _FefoList({required this.batches});
  @override
  State<_FefoList> createState() => _FefoListState();
}

class _FefoListState extends State<_FefoList> {
  String _search = '';

  List<Map<String, dynamic>> get _filtered {
    if (_search.isEmpty) return widget.batches;
    final q = _search.toLowerCase();
    return widget.batches.where((b) {
      final p = b['products'] as Map<String, dynamic>?;
      final name = (p?['name'] as String? ?? '').toLowerCase();
      final cat  = (p?['category'] as String? ?? '').toLowerCase();
      return name.contains(q) || cat.contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final all = widget.batches;
    final todayItems  = all.where((b) { final d = _daysLeft(b['expiry_date'] ?? ''); return d <= 0; }).length;
    final critItems   = all.where((b) { final d = _daysLeft(b['expiry_date'] ?? ''); return d == 1; }).length;
    final urgentItems = all.where((b) { final d = _daysLeft(b['expiry_date'] ?? ''); return d >= 2 && d <= 3; }).length;
    final normalItems = (all.length - todayItems - critItems - urgentItems).clamp(0, all.length);
    final filtered    = _filtered;

    if (all.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.check_circle, size: 56, color: Color(0xFF22C55E)),
            SizedBox(height: 12),
            Text('Sin productos próximos a caducar',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.grey)),
            SizedBox(height: 4),
            Text('El inventario está bajo control', style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }

    return Column(
      children: [
        // Stats header
        Container(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
          decoration: const BoxDecoration(color: Color(0xFFF8FAFC)),
          child: Column(children: [
            Row(children: [
              _FefoStatBadge('${all.length}', 'total', const Color(0xFF6B7280)),
              const SizedBox(width: 8),
              if (todayItems > 0) ...[
                _FefoStatBadge('$todayItems', 'hoy', const Color(0xFFEF4444)),
                const SizedBox(width: 8),
              ],
              if (critItems > 0) ...[
                _FefoStatBadge('$critItems', '1 día', const Color(0xFFF97316)),
                const SizedBox(width: 8),
              ],
              if (urgentItems > 0) ...[
                _FefoStatBadge('$urgentItems', '2-3 días', const Color(0xFFD97706)),
                const SizedBox(width: 8),
              ],
              const Spacer(),
              const Text('FEFO · First Expired First Out',
                  style: TextStyle(fontSize: 9, color: Colors.grey, fontStyle: FontStyle.italic)),
            ]),
            const SizedBox(height: 8),
            // Urgency distribution bar
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: SizedBox(
                height: 6,
                child: Row(children: [
                  if (todayItems > 0) Expanded(flex: todayItems, child: Container(color: const Color(0xFFEF4444))),
                  if (critItems > 0) Expanded(flex: critItems, child: Container(color: const Color(0xFFF97316))),
                  if (urgentItems > 0) Expanded(flex: urgentItems, child: Container(color: const Color(0xFFD97706))),
                  if (normalItems > 0) Expanded(flex: normalItems, child: Container(color: const Color(0xFF10B981))),
                ]),
              ),
            ),
            const SizedBox(height: 8),
            const Divider(height: 1, color: Color(0xFFE2E8F0)),
          ]),
        ),
        // Search bar
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: TextField(
            onChanged: (v) => setState(() => _search = v),
            decoration: InputDecoration(
              hintText: 'Buscar producto o categoría…',
              hintStyle: const TextStyle(fontSize: 13),
              prefixIcon: const Icon(Icons.search, size: 18),
              suffixIcon: _search.isNotEmpty
                  ? IconButton(icon: const Icon(Icons.clear, size: 16), onPressed: () => setState(() => _search = ''))
                  : null,
              filled: true,
              fillColor: Colors.white,
              contentPadding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: Color(0xFFE2E8F0))),
            ),
          ),
        ),
        if (filtered.isEmpty)
          Expanded(child: Center(child: Text('Sin resultados para "$_search"', style: const TextStyle(color: Colors.grey))))
        else
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
              itemCount: filtered.length,
              itemBuilder: (context, index) {
                final b = filtered[index];
                final product = b['products'] as Map<String, dynamic>?;
                final name     = product?['name'] as String? ?? 'Producto';
                final category = product?['category'] as String? ?? '';
                final pasillo  = (product?['pasillo'] as String?)?.isNotEmpty == true ? product!['pasillo'] as String : 'Sin ubicación';
                final est      = product?['estanteria'] as String?;
                final niv      = product?['nivel'] as String?;
                final expiry   = b['expiry_date'] as String? ?? '';
                final qty      = b['quantity'] as int? ?? 0;
                final price    = (product?['price'] as num?)?.toDouble() ?? 0.0;
                final days     = _daysLeft(expiry);
                final color    = _urgencyColor(days);
                final val      = qty * price;

                // Badge de días
                String badgeText;
                Color badgeColor;
                if (days <= 0) {
                  badgeText = 'HOY';
                  badgeColor = const Color(0xFFEF4444);
                } else if (days == 1) {
                  badgeText = '1 DÍA';
                  badgeColor = const Color(0xFFF97316);
                } else if (days <= 3) {
                  badgeText = '$days DÍAS';
                  badgeColor = const Color(0xFFD97706);
                } else {
                  badgeText = '$days d.';
                  badgeColor = const Color(0xFF10B981);
                }

                return GestureDetector(
                  onTap: () => showPasilloDetail(context, pasillo, [b]),
                  child: Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border(left: BorderSide(color: color, width: 5)),
                    boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 6, offset: const Offset(0, 2))],
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    child: Row(children: [
                      // Icono categoría
                      Container(
                        width: 40, height: 40,
                        decoration: BoxDecoration(
                          color: color.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(_categoryIcon(category), color: color, size: 20),
                      ),
                      const SizedBox(width: 10),
                      // Info
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                        const SizedBox(height: 3),
                        Row(children: [
                          Icon(Icons.map_outlined, size: 11, color: Colors.grey[500]),
                          const SizedBox(width: 3),
                          Flexible(
                            child: Text(
                              'P.$pasillo${est != null && est.isNotEmpty ? ' · E.$est' : ''}${niv != null && niv.isNotEmpty ? ' · N.$niv' : ''}',
                              style: TextStyle(fontSize: 11, color: Colors.grey[600]),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Icon(Icons.inventory_2_outlined, size: 11, color: Colors.grey[500]),
                          const SizedBox(width: 3),
                          Text('$qty uds', style: TextStyle(fontSize: 11, color: Colors.grey[600])),
                          const SizedBox(width: 8),
                          Text('${val.toStringAsFixed(2)} €', style: const TextStyle(fontSize: 11, color: Color(0xFF059669), fontWeight: FontWeight.w600)),
                        ]),
                        if (category.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(category, style: TextStyle(fontSize: 10, color: Colors.grey[400])),
                        ],
                      ])),
                      // Badge días
                      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                          decoration: BoxDecoration(
                            color: badgeColor,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(badgeText, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 11)),
                        ),
                        const SizedBox(height: 4),
                        Text(expiry, style: TextStyle(fontSize: 10, color: Colors.grey[500])),
                      ]),
                    ]),
                  ),
                  ),
                );
              },
            ),
          ),
      ],
    );
  }
}

class _FefoStatBadge extends StatelessWidget {
  final String count;
  final String label;
  final Color color;
  const _FefoStatBadge(this.count, this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: color.withValues(alpha: 0.3)),
    ),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Text(count, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: color)),
      const SizedBox(width: 4),
      Text(label, style: TextStyle(fontSize: 10, color: color)),
    ]),
  );
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

// ── Almacén Quick Tab ─────────────────────────────────────────────────────────

class _WarehouseQuickTab extends ConsumerWidget {
  const _WarehouseQuickTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final warehouseAsync = ref.watch(_warehouseQuickProvider);
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(_warehouseQuickProvider),
      child: warehouseAsync.when(
        loading: () => const ShimmerList(count: 6, itemHeight: 72),
        error: (_, __) => Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.warehouse_outlined, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('No se pudo cargar el almacén', style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed: () => ref.invalidate(_warehouseQuickProvider),
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Reintentar'),
            ),
          ]),
        ),
        data: (data) {
          final items = List<Map<String, dynamic>>.from(data['items'] ?? []);
          final totalValue = (data['total_value'] as num?)?.toDouble() ?? 0;
          final criticalCount = data['critical_count'] as int? ?? 0;
          final lowCount = data['low_count'] as int? ?? 0;

          // Sort: critical first, then low, then ok
          items.sort((a, b) {
            const order = {'critical': 0, 'low': 1, 'ok': 2};
            return (order[a['status']] ?? 2).compareTo(order[b['status']] ?? 2);
          });

          return ListView(
            padding: const EdgeInsets.all(14),
            children: [
              // Header card
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF0F172A), Color(0xFF1E3A5F)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    const Icon(Icons.warehouse_outlined, color: Colors.white, size: 20),
                    const SizedBox(width: 8),
                    const Expanded(child: Text('Almacén',
                        style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w800))),
                    if (criticalCount > 0)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(color: const Color(0xFFEF4444), borderRadius: BorderRadius.circular(6)),
                        child: Text('$criticalCount sin stock', style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
                      ),
                  ]),
                  const SizedBox(height: 10),
                  Row(children: [
                    _WStatPill('${items.length}', 'productos'),
                    const SizedBox(width: 8),
                    _WStatPill('${totalValue.toStringAsFixed(0)} €', 'valor'),
                    const SizedBox(width: 8),
                    if (lowCount > 0) _WStatPill('$lowCount', 'bajo stock', warn: true),
                  ]),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => context.push('/warehouse'),
                      icon: const Icon(Icons.open_in_new, size: 16, color: Colors.white),
                      label: const Text('Abrir almacén completo', style: TextStyle(color: Colors.white)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.white30),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                      ),
                    ),
                  ),
                ]),
              ),
              const SizedBox(height: 12),
              if (criticalCount > 0 || lowCount > 0) ...[
                const Text('⚠️ Requieren atención',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFFEF4444))),
                const SizedBox(height: 8),
              ],
              ...items.take(15).map((item) {
                final name = item['product_name'] as String? ?? 'Producto';
                final cat = item['category'] as String? ?? '';
                final qty = item['quantity'] as int? ?? 0;
                final status = item['status'] as String? ?? 'ok';
                final unit = item['unit'] as String? ?? 'uds';
                final statusColor = status == 'critical'
                    ? const Color(0xFFEF4444)
                    : status == 'low' ? const Color(0xFFD97706) : const Color(0xFF059669);
                return Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(10),
                    border: Border(left: BorderSide(color: statusColor, width: 3)),
                  ),
                  child: Row(children: [
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                      Text(cat, style: const TextStyle(fontSize: 11, color: Colors.grey)),
                    ])),
                    Text('$qty $unit', style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w800, color: statusColor)),
                  ]),
                );
              }),
              if (items.length > 15)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: TextButton.icon(
                    onPressed: () => context.push('/warehouse'),
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: Text('Ver los ${items.length - 15} productos restantes'),
                  ),
                ),
              const SizedBox(height: 16),
            ],
          );
        },
      ),
    );
  }
}

final _warehouseQuickProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  return ApiService().getWarehouseStock();
});

class _InlineWarehouseCard extends ConsumerWidget {
  final List<Map<String, dynamic>> batches;
  const _InlineWarehouseCard({required this.batches});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final warehouseAsync = ref.watch(_warehouseQuickProvider);

    // Calcula stats de caducidad de los lotes del plano
    int batchCritical = 0, batchUrgent = 0;
    for (final b in batches) {
      final expiry = b['expiry_date'] as String? ?? '';
      if (expiry.isEmpty) continue;
      try {
        final d = DateTime.parse(expiry).difference(DateTime.now()).inDays;
        if (d <= 1) { batchCritical++; } else if (d <= 3) { batchUrgent++; }
      } catch (_) {}
    }

    return GestureDetector(
      onTap: () => GoRouter.of(context).go('/warehouse'),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF1E293B), Color(0xFF0F3460)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(14),
          boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.2), blurRadius: 10, offset: const Offset(0, 4))],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Cabecera
          Row(children: [
            const Icon(Icons.warehouse_rounded, color: Colors.white, size: 20),
            const SizedBox(width: 8),
            const Expanded(
              child: Text('Almacén & Inventario',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 14)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
              child: const Row(mainAxisSize: MainAxisSize.min, children: [
                Text('Ver todo', style: TextStyle(color: Colors.white70, fontSize: 10)),
                SizedBox(width: 3),
                Icon(Icons.arrow_forward, color: Colors.white54, size: 11),
              ]),
            ),
          ]),
          const SizedBox(height: 12),
          // Stats del warehouse (datos reales)
          warehouseAsync.when(
            loading: () => const SizedBox(
              height: 36,
              child: Center(child: LinearProgressIndicator(backgroundColor: Colors.white12, color: Colors.white38)),
            ),
            error: (_, __) => Row(children: [
              _WInlineStat('${batches.length}', 'lotes plano', const Color(0xFF60A5FA)),
              const SizedBox(width: 12),
              if (batchCritical > 0) _WInlineStat('$batchCritical', 'vencen hoy', const Color(0xFFF87171)),
              if (batchUrgent > 0) _WInlineStat('$batchUrgent', 'en 3 días', const Color(0xFF3B82F6)),
            ]),
            data: (data) {
              final items = List<Map<String, dynamic>>.from(data['items'] ?? []);
              final totalValue = (data['total_value'] as num?)?.toDouble() ?? 0;
              final criticalCount = data['critical_count'] as int? ?? 0;
              final lowCount = data['low_count'] as int? ?? 0;
              return Row(children: [
                _WInlineStat('${items.length}', 'productos', const Color(0xFF60A5FA)),
                const SizedBox(width: 12),
                _WInlineStat('${totalValue.toStringAsFixed(0)} €', 'valor', const Color(0xFF34D399)),
                const SizedBox(width: 12),
                if (criticalCount > 0) _WInlineStat('$criticalCount', 'sin stock', const Color(0xFFF87171)),
                if (criticalCount == 0 && lowCount > 0) _WInlineStat('$lowCount', 'bajo stock', const Color(0xFF3B82F6)),
                if (criticalCount == 0 && lowCount == 0) _WInlineStat('OK', 'todo en orden', const Color(0xFF34D399)),
              ]);
            },
          ),
          // Alertas de caducidad si hay
          if (batchCritical > 0 || batchUrgent > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: batchCritical > 0 ? const Color(0xFFEF4444).withValues(alpha: 0.18) : const Color(0xFFD97706).withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(children: [
                Icon(Icons.warning_amber_rounded, size: 13,
                    color: batchCritical > 0 ? const Color(0xFFF87171) : const Color(0xFF3B82F6)),
                const SizedBox(width: 6),
                Expanded(child: Text(
                  batchCritical > 0
                      ? '$batchCritical lotes caducan hoy en tienda — acción urgente'
                      : '$batchUrgent lotes caducan en menos de 3 días',
                  style: TextStyle(
                      fontSize: 11,
                      color: batchCritical > 0 ? const Color(0xFFFCA5A5) : const Color(0xFFFDE68A),
                      fontWeight: FontWeight.w600),
                )),
              ]),
            ),
          ],
        ]),
      ),
    );
  }
}

class _WInlineStat extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _WInlineStat(this.value, this.label, this.color);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(value, style: TextStyle(color: color, fontSize: 16, fontWeight: FontWeight.w900)),
    Text(label, style: const TextStyle(color: Colors.white54, fontSize: 9)),
  ]);
}


class _WStatPill extends StatelessWidget {
  final String value, label;
  final bool warn;
  const _WStatPill(this.value, this.label, {this.warn = false});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(
      color: warn ? const Color(0xFFEF4444).withValues(alpha: 0.2) : Colors.white.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(7),
    ),
    child: Column(children: [
      Text(value, style: TextStyle(
          color: warn ? const Color(0xFFFCA5A5) : Colors.white,
          fontSize: 14, fontWeight: FontWeight.w800)),
      Text(label, style: const TextStyle(color: Colors.white54, fontSize: 9)),
    ]),
  );
}
