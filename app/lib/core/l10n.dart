import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ── String tables ─────────────────────────────────────────────────────────────

const _es = {
  // Navigation
  'nav_dashboard': 'Dashboard',
  'nav_scan': 'Escanear',
  'nav_actions': 'Acciones',
  'nav_map': 'Mapa',
  'nav_reports': 'Informes',
  // Screen titles
  'title_dashboard': 'MermaOps',
  'title_scan': 'Escanear producto',
  'title_actions': 'Acciones',
  'title_map': 'Mapa de tienda',
  'title_reports': 'Informes',
  // Action types
  'action_rebajar': 'Rebajar',
  'action_retirar': 'Retirar',
  'action_donar': 'Donar',
  'action_mover': 'Mover',
  'action_reponer': 'Reponer',
  'action_revisar': 'Revisar',
  // Tabs
  'tab_pending': 'Pendientes',
  'tab_history': 'Historial',
  'tab_daily': 'Diarios',
  'tab_weekly': 'Semanales',
  'tab_monthly': 'Mensual',
  'tab_merma': 'Merma',
  'tab_suppliers': 'Proveedores',
  'tab_orders': 'Pedidos',
  // Map
  'tab_map': 'Mapa de pasillos',
  'tab_fefo': 'Lista FEFO',
  // Dashboard
  'pending_actions': 'Acciones\npendientes',
  'critical_now': 'Críticas\nahora',
  'value_at_risk': 'Valor\nen riesgo',
  'expiring_7d': 'Productos\ncaducan 7d',
  'quick_actions': 'Acciones rápidas',
  'scan_product': 'Escanear\nproducto',
  'daily_route': 'Ruta\ndel día',
  'generate_brief': 'Generar\nbrief',
  // Common
  'refresh': 'Actualizar',
  'close': 'Cerrar',
  'confirm': 'Confirmar',
  'cancel': 'Cancelar',
  'export_csv': 'Exportar CSV',
  'import_csv': 'Importar CSV',
  'today': 'Hoy',
  'units': 'uds',
};

const _en = {
  // Navigation
  'nav_dashboard': 'Dashboard',
  'nav_scan': 'Scan',
  'nav_actions': 'Actions',
  'nav_map': 'Store Map',
  'nav_reports': 'Reports',
  // Screen titles
  'title_dashboard': 'MermaOps',
  'title_scan': 'Scan product',
  'title_actions': 'Actions',
  'title_map': 'Store map',
  'title_reports': 'Reports',
  // Action types
  'action_rebajar': 'Discount',
  'action_retirar': 'Remove',
  'action_donar': 'Donate',
  'action_mover': 'Move',
  'action_reponer': 'Restock',
  'action_revisar': 'Check',
  // Tabs
  'tab_pending': 'Pending',
  'tab_history': 'History',
  'tab_daily': 'Daily',
  'tab_weekly': 'Weekly',
  'tab_monthly': 'Monthly',
  'tab_merma': 'Waste',
  'tab_suppliers': 'Suppliers',
  'tab_orders': 'Orders',
  // Map
  'tab_map': 'Aisle map',
  'tab_fefo': 'FEFO list',
  // Dashboard
  'pending_actions': 'Pending\nactions',
  'critical_now': 'Critical\nnow',
  'value_at_risk': 'Value\nat risk',
  'expiring_7d': 'Products\nexpiring 7d',
  'quick_actions': 'Quick actions',
  'scan_product': 'Scan\nproduct',
  'daily_route': 'Daily\nroute',
  'generate_brief': 'Generate\nbrief',
  // Common
  'refresh': 'Refresh',
  'close': 'Close',
  'confirm': 'Confirm',
  'cancel': 'Cancel',
  'export_csv': 'Export CSV',
  'import_csv': 'Import CSV',
  'today': 'Today',
  'units': 'units',
};

// ── Provider ──────────────────────────────────────────────────────────────────

final languageProvider =
    StateNotifierProvider<LanguageNotifier, String>((ref) => LanguageNotifier());

class LanguageNotifier extends StateNotifier<String> {
  LanguageNotifier() : super('es') {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = prefs.getString('app_language') ?? 'es';
  }

  Future<void> toggle() async {
    state = state == 'es' ? 'en' : 'es';
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('app_language', state);
  }
}

// ── Helper function ───────────────────────────────────────────────────────────

String tr(WidgetRef ref, String key) {
  final lang = ref.watch(languageProvider);
  return lang == 'en' ? (_en[key] ?? key) : (_es[key] ?? key);
}

String trAction(WidgetRef ref, String actionType) {
  return tr(ref, 'action_$actionType');
}
