import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/store_provider.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart' show ShimmerList;
import '../../core/user_role_provider.dart';

final _warehouseProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  try {
    return await ApiService().getWarehouseStock();
  } catch (_) {
    // Backend down — query Supabase directly
    final sid = ref.read(resolvedStoreIdProvider);
    final rows = await supabase
        .from('warehouse_stock')
        .select('*, products(name, category, price, unit)')
        .eq('store_id', sid)
        .order('quantity');

    final items = <Map<String, dynamic>>[];
    int criticalCount = 0, lowCount = 0;
    double totalValue = 0;
    int totalUnits = 0;

    for (final row in rows) {
      final product = row['products'] as Map<String, dynamic>?;
      final qty = (row['quantity'] as int?) ?? 0;
      final minQty = (row['min_quantity'] as int?) ?? 5;
      final price = (product?['price'] as num?)?.toDouble() ?? 0.0;

      final String status;
      if (qty == 0 || qty < (minQty * 0.3).ceil()) {
        status = 'critical';
        criticalCount++;
      } else if (qty < minQty) {
        status = 'low';
        lowCount++;
      } else {
        status = 'ok';
      }

      totalValue += qty * price;
      totalUnits += qty;

      items.add({
        'id': row['id'],
        'product_id': row['product_id'],
        'product_name': product?['name'] ?? 'Producto',
        'category': product?['category'] ?? 'otros',
        'quantity': qty,
        'min_quantity': minQty,
        'unit': product?['unit'] ?? row['unit'] ?? 'uds',
        'status': status,
        'price': price,
        'updated_at': row['updated_at'],
      });
    }

    return {
      'items': items,
      'total_products': items.length,
      'total_units': totalUnits,
      'total_value': totalValue,
      'critical_count': criticalCount,
      'low_count': lowCount,
    };
  }
});

const _categoryIcons = <String, IconData>{
  'panaderia': Icons.bakery_dining,
  'lacteos': Icons.water_drop_outlined,
  'carne': Icons.set_meal,
  'carniceria': Icons.set_meal,
  'pescado': Icons.phishing,
  'pescaderia': Icons.phishing,
  'frutas': Icons.eco,
  'verduras': Icons.eco,
  'frutas y verduras': Icons.eco,
  'congelados': Icons.ac_unit,
  'bebidas': Icons.local_drink_outlined,
  'limpieza': Icons.cleaning_services_outlined,
};

const _categoryColors = <String, Color>{
  'panaderia': Color(0xFFF59E0B),
  'lacteos': Color(0xFF3B82F6),
  'carne': Color(0xFFEF4444),
  'carniceria': Color(0xFFEF4444),
  'pescado': Color(0xFF06B6D4),
  'pescaderia': Color(0xFF06B6D4),
  'frutas': Color(0xFF10B981),
  'verduras': Color(0xFF10B981),
  'frutas y verduras': Color(0xFF10B981),
  'congelados': Color(0xFF8B5CF6),
  'bebidas': Color(0xFF6366F1),
};

Color _catColor(String cat) =>
    _categoryColors[cat.toLowerCase()] ?? const Color(0xFF64748B);

IconData _catIcon(String cat) =>
    _categoryIcons[cat.toLowerCase()] ?? Icons.inventory_2_outlined;

class WarehouseScreen extends ConsumerStatefulWidget {
  const WarehouseScreen({super.key});
  @override
  ConsumerState<WarehouseScreen> createState() => _WarehouseScreenState();
}

class _WarehouseScreenState extends ConsumerState<WarehouseScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  String _search = '';
  String _filterCat = 'Todas';
  String _filterStatus = 'Todos';

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(_warehouseProvider);
    return Scaffold(
      backgroundColor: const Color(0xFFF1F5F9),
      appBar: AppBar(
        title: const Text('Almacén'),
        backgroundColor: const Color(0xFF0F172A),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 18),
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/map');
            }
          },
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(_warehouseProvider),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: const Color(0xFF059669),
          tabs: const [
            Tab(text: 'Inventario'),
            Tab(text: 'Por categoría'),
          ],
        ),
      ),
      body: async.when(
        loading: () => const ShimmerList(count: 8, itemHeight: 72),
        error: (e, _) => AppErrorWidget(
          error: e,
          customMessage: 'No se pudo cargar el inventario.',
          onRetry: () => ref.invalidate(_warehouseProvider),
        ),
        data: (data) => TabBarView(
          controller: _tabs,
          children: [
            _InventoryTab(data: data, search: _search, filterCat: _filterCat,
                filterStatus: _filterStatus,
                onSearch: (v) => setState(() => _search = v),
                onCatFilter: (v) => setState(() => _filterCat = v),
                onStatusFilter: (v) => setState(() => _filterStatus = v),
                onUpdate: (pid, qty) => _updateStock(pid, qty)),
            _CategoryTab(data: data),
          ],
        ),
      ),
    );
  }

  Future<void> _updateStock(String productId, int currentQty) async {
    final role = ref.read(userRoleProvider).valueOrNull;
    if (role == UserRole.staff) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Solo el encargado puede modificar el stock.')),
      );
      return;
    }
    final controller = TextEditingController(text: '$currentQty');
    final result = await showDialog<int>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Actualizar stock almacén'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Nueva cantidad',
            border: OutlineInputBorder(),
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          ElevatedButton(
            onPressed: () {
              final v = int.tryParse(controller.text);
              if (v != null && v >= 0) Navigator.pop(ctx, v);
            },
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
    if (result == null) return;
    try {
      await ApiService().updateWarehouseStock(productId, result);
      ref.invalidate(_warehouseProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Stock actualizado'), backgroundColor: Color(0xFF059669)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }
}

// ── Tab Inventario ────────────────────────────────────────────────────────────

class _InventoryTab extends StatelessWidget {
  final Map<String, dynamic> data;
  final String search, filterCat, filterStatus;
  final ValueChanged<String> onSearch, onCatFilter, onStatusFilter;
  final void Function(String, int) onUpdate;

  const _InventoryTab({
    required this.data,
    required this.search,
    required this.filterCat,
    required this.filterStatus,
    required this.onSearch,
    required this.onCatFilter,
    required this.onStatusFilter,
    required this.onUpdate,
  });

  @override
  Widget build(BuildContext context) {
    final items = List<Map<String, dynamic>>.from(data['items'] ?? []);
    final totalProducts = data['total_products'] as int? ?? 0;
    final totalUnits = data['total_units'] as int? ?? 0;
    final totalValue = (data['total_value'] as num?)?.toDouble() ?? 0;
    final criticalCount = data['critical_count'] as int? ?? 0;
    final lowCount = data['low_count'] as int? ?? 0;

    // Categorías únicas para filtro
    final categories = ['Todas', ...{...items.map((i) => i['category'] as String? ?? 'otros')}];

    // Filtro
    var filtered = items.where((i) {
      final cat = i['category'] as String? ?? '';
      final name = (i['product_name'] as String? ?? '').toLowerCase();
      final status = i['status'] as String? ?? '';
      if (filterCat != 'Todas' && cat != filterCat) return false;
      if (filterStatus != 'Todos' && status != filterStatus) return false;
      if (search.isNotEmpty && !name.contains(search.toLowerCase())) return false;
      return true;
    }).toList();

    return RefreshIndicator(
      onRefresh: () async {},
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          // Stats header
          _StatsHeader(
            totalProducts: totalProducts, totalUnits: totalUnits,
            totalValue: totalValue, criticalCount: criticalCount, lowCount: lowCount,
          ),
          const SizedBox(height: 14),

          // Search
          TextField(
            onChanged: onSearch,
            decoration: InputDecoration(
              hintText: 'Buscar producto…',
              prefixIcon: const Icon(Icons.search, size: 20),
              filled: true, fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(vertical: 10),
              suffixIcon: search.isNotEmpty
                  ? IconButton(icon: const Icon(Icons.clear, size: 18), onPressed: () => onSearch(''))
                  : null,
            ),
          ),
          const SizedBox(height: 10),

          // Filtros fila
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              ...['Todos', 'critical', 'low', 'ok'].map((s) => _FilterChip(
                label: s == 'Todos' ? 'Todos' : s == 'critical' ? '🔴 Crítico' : s == 'low' ? '🟡 Bajo' : '🟢 OK',
                selected: filterStatus == s,
                onTap: () => onStatusFilter(s),
              )),
              const SizedBox(width: 12),
              ...categories.take(6).map((c) => _FilterChip(
                label: c == 'Todas' ? 'Todas' : c,
                selected: filterCat == c,
                onTap: () => onCatFilter(c),
                color: c == 'Todas' ? null : _catColor(c),
              )),
            ]),
          ),
          const SizedBox(height: 12),

          Text('${filtered.length} productos', style: const TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 8),

          if (filtered.isEmpty)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Text('Sin resultados', style: TextStyle(color: Colors.grey)),
              ),
            )
          else
            ...filtered.map((item) => _WarehouseItemCard(item: item, onUpdate: onUpdate)),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _StatsHeader extends StatelessWidget {
  final int totalProducts, totalUnits, criticalCount, lowCount;
  final double totalValue;
  const _StatsHeader({
    required this.totalProducts, required this.totalUnits,
    required this.totalValue, required this.criticalCount, required this.lowCount,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      gradient: const LinearGradient(
        colors: [Color(0xFF0F172A), Color(0xFF1E3A5F)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const Icon(Icons.warehouse_outlined, color: Colors.white, size: 22),
        const SizedBox(width: 10),
        const Expanded(child: Text('Inventario Almacén',
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800))),
        if (criticalCount > 0)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: const Color(0xFFEF4444),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text('$criticalCount críticos',
                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
          ),
      ]),
      const SizedBox(height: 14),
      Row(children: [
        _StatBox(value: '$totalProducts', label: 'productos'),
        const SizedBox(width: 10),
        _StatBox(value: '$totalUnits', label: 'unidades'),
        const SizedBox(width: 10),
        _StatBox(value: '${totalValue.toStringAsFixed(0)}€', label: 'valor'),
        const SizedBox(width: 10),
        _StatBox(value: '$lowCount', label: 'bajo stock', warn: lowCount > 0),
      ]),
    ]),
  );
}

class _StatBox extends StatelessWidget {
  final String value, label;
  final bool warn;
  const _StatBox({required this.value, required this.label, this.warn = false});
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: warn ? const Color(0xFFEF4444).withValues(alpha: 0.25) : Colors.white.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(children: [
      Text(value, style: TextStyle(
          color: warn ? const Color(0xFFFCA5A5) : Colors.white,
          fontSize: 15, fontWeight: FontWeight.w800)),
      Text(label, style: const TextStyle(color: Colors.white54, fontSize: 9)),
    ]),
  );
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Color? color;
  const _FilterChip({required this.label, required this.selected, required this.onTap, this.color});
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      margin: const EdgeInsets.only(right: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: selected ? (color ?? const Color(0xFF059669)) : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: selected ? Colors.transparent : const Color(0xFFE5E7EB)),
      ),
      child: Text(label, style: TextStyle(
          fontSize: 12, fontWeight: FontWeight.w600,
          color: selected ? Colors.white : (color ?? Colors.grey[700]))),
    ),
  );
}

class _WarehouseItemCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final void Function(String, int) onUpdate;
  const _WarehouseItemCard({required this.item, required this.onUpdate});

  @override
  Widget build(BuildContext context) {
    final name = item['product_name'] as String? ?? 'Producto';
    final cat = item['category'] as String? ?? '';
    final qty = item['quantity'] as int? ?? 0;
    final value = (item['value'] as num?)?.toDouble() ?? 0;
    final status = item['status'] as String? ?? 'ok';
    final pid = item['product_id'] as String? ?? '';
    final unit = item['unit'] as String? ?? 'uds';

    final statusColor = status == 'critical'
        ? const Color(0xFFEF4444)
        : status == 'low'
            ? const Color(0xFFF59E0B)
            : const Color(0xFF059669);

    final catColor = _catColor(cat);
    final catIcon = _catIcon(cat);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: statusColor, width: 3)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4, offset: const Offset(0, 2))],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        leading: Container(
          width: 40, height: 40,
          decoration: BoxDecoration(
            color: catColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(catIcon, color: catColor, size: 20),
        ),
        title: Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
        subtitle: Row(children: [
          Text(cat, style: const TextStyle(fontSize: 11, color: Colors.grey)),
          const SizedBox(width: 8),
          Text('${value.toStringAsFixed(2)} €', style: const TextStyle(fontSize: 11, color: Colors.grey)),
        ]),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('$qty $unit', style: TextStyle(
                fontSize: 18, fontWeight: FontWeight.w800, color: statusColor)),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                status == 'critical' ? 'CRÍTICO' : status == 'low' ? 'BAJO' : 'OK',
                style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: statusColor),
              ),
            ),
          ]),
          const SizedBox(width: 6),
          IconButton(
            icon: const Icon(Icons.edit_outlined, size: 18, color: Colors.grey),
            onPressed: () => onUpdate(pid, qty),
          ),
        ]),
      ),
    );
  }
}

// ── Tab Por categoría ─────────────────────────────────────────────────────────

class _CategoryTab extends StatelessWidget {
  final Map<String, dynamic> data;
  const _CategoryTab({required this.data});

  @override
  Widget build(BuildContext context) {
    final byCategory = List<Map<String, dynamic>>.from(data['by_category'] ?? []);
    final items = List<Map<String, dynamic>>.from(data['items'] ?? []);
    byCategory.sort((a, b) => ((b['value'] as num?) ?? 0).compareTo((a['value'] as num?) ?? 0));

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        const Text('Distribución por categoría',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
        const SizedBox(height: 12),
        ...byCategory.map((cat) {
          final catName = cat['category'] as String? ?? '';
          final catItems = int.tryParse('${cat['items']}') ?? 0;
          final catUnits = int.tryParse('${cat['units']}') ?? 0;
          final catValue = (cat['value'] as num?)?.toDouble() ?? 0;
          final catColor = _catColor(catName);
          final catIcon = _catIcon(catName);
          final totalValue = (data['total_value'] as num?)?.toDouble() ?? 1;
          final fraction = totalValue > 0 ? (catValue / totalValue).clamp(0.0, 1.0) : 0.0;

          // Items críticos en esta categoría
          final criticalInCat = items.where((i) =>
              i['category'] == catName && i['status'] == 'critical').length;

          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: criticalInCat > 0
                  ? const Color(0xFFEF4444).withValues(alpha: 0.3)
                  : const Color(0xFFE5E7EB)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Container(
                  width: 38, height: 38,
                  decoration: BoxDecoration(
                    color: catColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(catIcon, color: catColor, size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(catName.isNotEmpty ? catName[0].toUpperCase() + catName.substring(1) : '',
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                  Text('$catItems productos · $catUnits uds',
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                ])),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('${catValue.toStringAsFixed(2)} €',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: catColor)),
                  Text('${(fraction * 100).toStringAsFixed(0)}% del total',
                      style: const TextStyle(fontSize: 10, color: Colors.grey)),
                ]),
              ]),
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: fraction,
                  minHeight: 6,
                  backgroundColor: const Color(0xFFF3F4F6),
                  valueColor: AlwaysStoppedAnimation<Color>(catColor),
                ),
              ),
              if (criticalInCat > 0) ...[
                const SizedBox(height: 8),
                Row(children: [
                  const Icon(Icons.warning_rounded, size: 14, color: Color(0xFFEF4444)),
                  const SizedBox(width: 4),
                  Text('$criticalInCat producto${criticalInCat > 1 ? 's' : ''} sin stock crítico',
                      style: const TextStyle(fontSize: 11, color: Color(0xFFEF4444), fontWeight: FontWeight.w600)),
                ]),
              ],
            ]),
          );
        }),
        const SizedBox(height: 16),
      ],
    );
  }
}
