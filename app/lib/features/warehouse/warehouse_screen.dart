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
  'panaderia': Color(0xFFD97706),
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
  bool _refreshing = false;

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
            icon: _refreshing
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.refresh),
            onPressed: _refreshing ? null : () async {
              setState(() => _refreshing = true);
              final messenger = ScaffoldMessenger.of(context);
              messenger.showSnackBar(
                const SnackBar(content: Text('Actualizando inventario...'), duration: Duration(seconds: 2)),
              );
              ref.invalidate(_warehouseProvider);
              await ref.read(_warehouseProvider.future).then((_) {
                if (mounted) {
                  setState(() => _refreshing = false);
                  messenger.showSnackBar(
                    const SnackBar(content: Text('Inventario actualizado'), backgroundColor: Color(0xFF059669), duration: Duration(seconds: 2)),
                  );
                }
              }).catchError((_) {
                if (mounted) setState(() => _refreshing = false);
              });
            },
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
            ? const Color(0xFFD97706)
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

    final totalValue = (data['total_value'] as num?)?.toDouble() ?? 1.0;
    final highestCatValue = byCategory.isEmpty ? 1.0 :
        byCategory.fold<double>(0, (m, c) => ((c['value'] as num?)?.toDouble() ?? 0) > m ? (c['value'] as num).toDouble() : m);

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        const Text('Distribución por categoría',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
        const SizedBox(height: 8),
        // Summary header — horizontal bar chart
        if (byCategory.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Valor por categoría', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
              const SizedBox(height: 10),
              ...byCategory.map((cat) {
                final catName = cat['category'] as String? ?? '';
                final catValue = (cat['value'] as num?)?.toDouble() ?? 0;
                final catColor = _catColor(catName);
                final ratio = highestCatValue > 0 ? (catValue / highestCatValue).clamp(0.0, 1.0) : 0.0;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(children: [
                    SizedBox(width: 80, child: Text(
                      catName.isNotEmpty ? catName[0].toUpperCase() + catName.substring(1) : '',
                      style: const TextStyle(fontSize: 10, color: Color(0xFF6B7280)),
                      overflow: TextOverflow.ellipsis,
                    )),
                    Expanded(child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: ratio,
                        minHeight: 8,
                        backgroundColor: const Color(0xFFF3F4F6),
                        valueColor: AlwaysStoppedAnimation<Color>(catColor),
                      ),
                    )),
                    const SizedBox(width: 8),
                    SizedBox(width: 52, child: Text(
                      '${catValue.toStringAsFixed(0)} €',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: catColor),
                      textAlign: TextAlign.right,
                    )),
                  ]),
                );
              }),
            ]),
          ),
          const SizedBox(height: 12),
        ],
        ..._buildCategoryCards(context, byCategory, items, totalValue),
        const SizedBox(height: 16),
      ],
    );
  }

  List<Widget> _buildCategoryCards(BuildContext context,
      List<Map<String, dynamic>> byCategory,
      List<Map<String, dynamic>> items,
      double totalValue) {
    return byCategory.map((cat) {
      final catName = cat['category'] as String? ?? '';
      final catItems = int.tryParse('${cat['items']}') ?? 0;
      final catUnits = int.tryParse('${cat['units']}') ?? 0;
      final catValue = (cat['value'] as num?)?.toDouble() ?? 0;
      final catColor = _catColor(catName);
      final catIcon = _catIcon(catName);
      final fraction = totalValue > 0 ? (catValue / totalValue).clamp(0.0, 1.0) : 0.0;

      final itemsInCat = items.where((i) => i['category'] == catName).toList();
      final criticalInCat = itemsInCat.where((i) => i['status'] == 'critical').length;
      final lowInCat = itemsInCat.where((i) => i['status'] == 'low').length;

      final borderColor = criticalInCat > 0
          ? const Color(0xFFEF4444)
          : lowInCat > 0
              ? const Color(0xFFD97706)
              : const Color(0xFF059669);

      // Top 3 items sorted by value desc
      final top3 = List<Map<String, dynamic>>.from(itemsInCat)
        ..sort((a, b) {
          final va = (a['quantity'] as int? ?? 0) * (a['price'] as num? ?? 0).toDouble();
          final vb = (b['quantity'] as int? ?? 0) * (b['price'] as num? ?? 0).toDouble();
          return vb.compareTo(va);
        });

      return _CategoryCard(
        catName: catName,
        catIcon: catIcon,
        catColor: catColor,
        catItems: catItems,
        catUnits: catUnits,
        catValue: catValue,
        fraction: fraction,
        criticalInCat: criticalInCat,
        lowInCat: lowInCat,
        borderColor: borderColor,
        top3: top3.take(3).toList(),
        totalItems: itemsInCat.length,
      );
    }).toList();
  }
}

class _CategoryCard extends StatefulWidget {
  final String catName;
  final IconData catIcon;
  final Color catColor;
  final int catItems, catUnits, criticalInCat, lowInCat, totalItems;
  final double catValue, fraction;
  final Color borderColor;
  final List<Map<String, dynamic>> top3;

  const _CategoryCard({
    required this.catName,
    required this.catIcon,
    required this.catColor,
    required this.catItems,
    required this.catUnits,
    required this.catValue,
    required this.fraction,
    required this.criticalInCat,
    required this.lowInCat,
    required this.borderColor,
    required this.top3,
    required this.totalItems,
  });

  @override
  State<_CategoryCard> createState() => _CategoryCardState();
}

class _CategoryCardState extends State<_CategoryCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final displayName = widget.catName.isNotEmpty
        ? widget.catName[0].toUpperCase() + widget.catName.substring(1)
        : '';

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border(
          left: BorderSide(color: widget.borderColor, width: 4),
          right: BorderSide(color: const Color(0xFFE5E7EB)),
          top: BorderSide(color: const Color(0xFFE5E7EB)),
          bottom: BorderSide(color: const Color(0xFFE5E7EB)),
        ),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4, offset: const Offset(0, 2))],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                width: 38, height: 38,
                decoration: BoxDecoration(
                  color: widget.catColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(widget.catIcon, color: widget.catColor, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(displayName, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                Text('${widget.catItems} productos · ${widget.catUnits} uds',
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ])),
              Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('${widget.catValue.toStringAsFixed(2)} €',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: widget.catColor)),
                Text('${(widget.fraction * 100).toStringAsFixed(0)}% del total',
                    style: const TextStyle(fontSize: 10, color: Colors.grey)),
              ]),
            ]),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: widget.fraction,
                minHeight: 6,
                backgroundColor: const Color(0xFFF3F4F6),
                valueColor: AlwaysStoppedAnimation<Color>(widget.catColor),
              ),
            ),
            const SizedBox(height: 8),
            // Status summary
            Row(children: [
              if (widget.criticalInCat > 0) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(color: const Color(0xFFEF4444).withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
                  child: Text('${widget.criticalInCat} crítico${widget.criticalInCat > 1 ? "s" : ""}',
                      style: const TextStyle(fontSize: 10, color: Color(0xFFEF4444), fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 6),
              ],
              if (widget.lowInCat > 0) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(color: const Color(0xFFD97706).withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
                  child: Text('${widget.lowInCat} bajo${widget.lowInCat > 1 ? "s" : ""}',
                      style: const TextStyle(fontSize: 10, color: Color(0xFFD97706), fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 6),
              ],
              if (widget.criticalInCat == 0 && widget.lowInCat == 0)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(color: const Color(0xFF059669).withValues(alpha: 0.1), borderRadius: BorderRadius.circular(4)),
                  child: const Text('Todo OK', style: TextStyle(fontSize: 10, color: Color(0xFF059669), fontWeight: FontWeight.w700)),
                ),
              const Spacer(),
              // Pedir reposición button
              GestureDetector(
                onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Pedido solicitado a proveedor — $displayName'), backgroundColor: const Color(0xFF059669)),
                ),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: widget.catColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: widget.catColor.withValues(alpha: 0.3)),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.add_shopping_cart_outlined, size: 12, color: widget.catColor),
                    const SizedBox(width: 4),
                    Text('Pedir reposición', style: TextStyle(fontSize: 10, color: widget.catColor, fontWeight: FontWeight.w600)),
                  ]),
                ),
              ),
            ]),
          ]),
        ),
        // Top 3 + expandable
        if (widget.top3.isNotEmpty) ...[
          const Divider(height: 1, color: Color(0xFFF3F4F6)),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 8, 14, 4),
            child: Text('Top productos', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.grey[600])),
          ),
          ...(_expanded ? widget.top3 : widget.top3.take(3)).map((item) {
            final name = item['product_name'] as String? ?? 'Producto';
            final qty = item['quantity'] as int? ?? 0;
            final status = item['status'] as String? ?? 'ok';
            final unit = item['unit'] as String? ?? 'uds';
            final statusColor = status == 'critical'
                ? const Color(0xFFEF4444)
                : status == 'low' ? const Color(0xFFD97706) : const Color(0xFF059669);
            return Padding(
              padding: const EdgeInsets.fromLTRB(14, 2, 14, 2),
              child: Row(children: [
                Container(width: 6, height: 6, decoration: BoxDecoration(color: statusColor, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Expanded(child: Text(name, style: const TextStyle(fontSize: 12, color: Color(0xFF374151)), overflow: TextOverflow.ellipsis)),
                Text('$qty $unit', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: statusColor)),
              ]),
            );
          }),
          if (widget.totalItems > 3)
            TextButton.icon(
              onPressed: () => setState(() => _expanded = !_expanded),
              icon: Icon(_expanded ? Icons.expand_less : Icons.chevron_right, size: 14),
              label: Text(_expanded ? 'Ver menos' : 'Ver todos (${widget.totalItems})',
                  style: const TextStyle(fontSize: 11)),
              style: TextButton.styleFrom(
                foregroundColor: widget.catColor,
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            )
          else
            const SizedBox(height: 8),
        ],
      ]),
    );
  }
}
