import 'dart:async';
import 'dart:convert';
import 'dart:math' show pi;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/l10n.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart' show UrgencyColors, ShimmerKpiGrid;

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

// ── Providers ─────────────────────────────────────────────────────────────────

final _comparisonProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  // Auto-refresh every 15 minutes
  final t = Timer(const Duration(minutes: 15), ref.invalidateSelf);
  ref.onDispose(t.cancel);
  return api.getStoresComparison();
});

final _weatherProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  // Auto-refresh every 30 minutes — datos meteorológicos en tiempo real
  final t = Timer(const Duration(minutes: 30), ref.invalidateSelf);
  ref.onDispose(t.cancel);
  return ApiService().getWeather();
});

final _predictionsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  // Auto-refresh every 30 minutes (weather + predictor data)
  final t = Timer(const Duration(minutes: 30), ref.invalidateSelf);
  ref.onDispose(t.cancel);
  return ApiService().getRiskPredictions(days: 7);
});

// Escucha cambios en acciones en tiempo real (Supabase Realtime)
final _actionsRealtimeProvider = StreamProvider<List<Map<String, dynamic>>>((ref) {
  return supabase
      .from('actions')
      .stream(primaryKey: ['id'])
      .eq('store_id', storeId);
});

const _dashCacheKey = 'dashboard_cache';
const _dashCacheTimeKey = 'dashboard_cache_time';

Future<void> _saveDashCache(Map<String, dynamic> data) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(_dashCacheKey, jsonEncode(data));
  await prefs.setInt(_dashCacheTimeKey, DateTime.now().millisecondsSinceEpoch);
}

Future<Map<String, dynamic>?> _loadDashCache() async {
  final prefs = await SharedPreferences.getInstance();
  final raw = prefs.getString(_dashCacheKey);
  if (raw == null) return null;
  try {
    final data = Map<String, dynamic>.from(jsonDecode(raw) as Map);
    final ts = prefs.getInt(_dashCacheTimeKey) ?? 0;
    data['_cached_at'] = ts;
    return data;
  } catch (_) {
    return null;
  }
}

final dashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  // Auto-refresh every 5 minutes to keep KPIs current
  final t = Timer(const Duration(minutes: 5), ref.invalidateSelf);
  ref.onDispose(t.cancel);
  final pending = await supabase
      .from('actions')
      .select('priority_score, action_type, batch_id')
      .eq('store_id', storeId)
      .eq('status', 'pending')
      .order('priority_score', ascending: false);

  final batches = await supabase
      .from('batches')
      .select('id, product_id, quantity, expiry_date')
      .eq('store_id', storeId)
      .eq('status', 'active')
      .lte('expiry_date',
          DateTime.now().add(const Duration(days: 7)).toIso8601String().substring(0, 10))
      .order('expiry_date', ascending: true);

  // Fetch products via backend (bypasses Supabase RLS on products table)
  Map<String, Map<String, dynamic>> productsMap = {};
  try {
    final prods = await api.getProducts();
    for (final p in prods) {
      productsMap[p['id'] as String] = Map<String, dynamic>.from(p);
    }
  } catch (_) {}

  final brief = await supabase
      .from('daily_briefs')
      .select()
      .eq('store_id', storeId)
      .order('date', ascending: false)
      .limit(1)
      .maybeSingle();

  double valueAtRisk = 0;
  Map<String, dynamic>? mostCritical;
  for (final b in batches) {
    final pid = b['product_id'] as String? ?? '';
    final product = productsMap[pid];
    final qty = (b['quantity'] as num?)?.toDouble() ?? 0;
    final price = (product?['price'] as num?)?.toDouble() ?? 0;
    valueAtRisk += qty * price;
    if (mostCritical == null) mostCritical = {...b, 'products': product};
  }

  final pendingList = List<Map<String, dynamic>>.from(pending);
  final criticalCount =
      pendingList.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length;
  final highCount =
      pendingList.where((a) => (a['priority_score'] as int? ?? 0) >= 65).length;

  final donationsRaw = await supabase
      .from('donations')
      .select('quantity, value_donated')
      .eq('store_id', storeId)
      .gte('donated_at',
          DateTime.now().subtract(const Duration(days: 30)).toIso8601String());
  final donations = List<Map<String, dynamic>>.from(donationsRaw);
  final donationQty = donations.fold<int>(0, (s, d) => s + ((d['quantity'] as int?) ?? 0));
  final donationValue = donations.fold<double>(
      0, (s, d) => s + ((d['value_donated'] as num?)?.toDouble() ?? 0));

  final cutoff7 = DateTime.now().subtract(const Duration(days: 7));
  final merma7 = await supabase
      .from('merma_log')
      .select('date, value_lost')
      .eq('store_id', storeId)
      .gte('date', cutoff7.toIso8601String().substring(0, 10))
      .order('date', ascending: true);

  final todayStr = DateTime.now().toIso8601String().substring(0, 10);
  final tomorrowStr = DateTime.now()
      .add(const Duration(days: 1))
      .toIso8601String()
      .substring(0, 10);
  final expiringTodayRaw = await supabase
      .from('batches')
      .select('id, product_id, quantity, expiry_date')
      .eq('store_id', storeId)
      .eq('status', 'active')
      .gte('expiry_date', todayStr)
      .lte('expiry_date', tomorrowStr)
      .order('expiry_date', ascending: true)
      .limit(6);
  final expiringToday = (expiringTodayRaw as List).map((b) {
    final pid = b['product_id'] as String? ?? '';
    return {...Map<String, dynamic>.from(b), 'products': productsMap[pid]};
  }).toList();

  final completedTodayRaw = await supabase
      .from('actions')
      .select('id')
      .eq('store_id', storeId)
      .eq('status', 'completed')
      .gte('completed_at', todayStr);

  // ── Predictive alerts: lotes que van a cruzar el umbral CRÍTICO pronto ────
  // Computa qué productos sin acción caducan en las próximas 24-48h
  // con alto stock → van a necesitar acción urgente antes de que sea tarde.
  final pendingBatchIds = pendingList.map((a) => a['batch_id']).toSet();
  final predictiveAlerts = <Map<String, dynamic>>[];
  final now = DateTime.now();
  for (final b in batches) {
    final batchId = b['id'] ?? '';
    if (pendingBatchIds.contains(batchId)) continue; // ya tiene acción
    final expiryStr = b['expiry_date'] as String? ?? '';
    if (expiryStr.isEmpty) continue;
    final expiry = DateTime.tryParse(expiryStr);
    if (expiry == null) continue;
    final hoursLeft = expiry.difference(now).inHours;
    if (hoursLeft < 0 || hoursLeft > 48) continue; // solo próximas 48h sin acción

    final product = productsMap[b['product_id'] as String? ?? ''] ?? {};
    final qty = (b['quantity'] as num?)?.toInt() ?? 0;
    final price = (product['price'] as num?)?.toDouble() ?? 0;
    final value = qty * price;

    if (value < 5) continue; // ignorar productos de poco valor

    predictiveAlerts.add({
      'product': product['name'] ?? 'Producto',
      'hours_left': hoursLeft,
      'days_left': expiry.difference(now).inDays,
      'qty': qty,
      'value': value,
      'pasillo': product['pasillo'] ?? '?',
      'expiry': expiryStr,
    });
  }
  predictiveAlerts.sort((a, b) => (a['hours_left'] as int).compareTo(b['hours_left'] as int));

  final result = {
    'pending_count': pendingList.length,
    'critical_count': criticalCount,
    'high_count': highCount,
    'value_at_risk': valueAtRisk,
    'brief': brief,
    'expiring_count': batches.length,
    'most_critical_batch': mostCritical,
    'merma_7d': List<Map<String, dynamic>>.from(merma7),
    'donation_qty': donationQty,
    'donation_value': donationValue,
    'expiring_today': List<Map<String, dynamic>>.from(expiringToday),
    'completed_today': (completedTodayRaw as List).length,
    'predictive_alerts': predictiveAlerts.take(4).toList(),
  };
  // Guardar en caché para modo offline
  await _saveDashCache(result);
  return result;
});

// ── Screen ────────────────────────────────────────────────────────────────────

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  int _prevCriticalCount = -1;

  @override
  Widget build(BuildContext context) {
    // Realtime: recarga dashboard y muestra banner si aparecen nuevos críticos
    ref.listen(_actionsRealtimeProvider, (prev, next) {
      ref.invalidate(dashboardProvider);
      next.whenData((actions) {
        final criticals = actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length;
        if (_prevCriticalCount >= 0 && criticals > _prevCriticalCount) {
          final newCount = criticals - _prevCriticalCount;
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Row(children: [
              const Icon(Icons.crisis_alert_rounded, color: Colors.white, size: 18),
              const SizedBox(width: 8),
              Expanded(child: Text('$newCount nuevo${newCount > 1 ? 's' : ''} producto${newCount > 1 ? 's' : ''} CRÍTICO${newCount > 1 ? 'S' : ''} detectado${newCount > 1 ? 's' : ''}')),
            ]),
            backgroundColor: const Color(0xFFDC2626),
            duration: const Duration(seconds: 5),
            action: SnackBarAction(
              label: 'Ver acciones',
              textColor: Colors.white,
              onPressed: () => context.go('/actions'),
            ),
          ));
        }
        setState(() => _prevCriticalCount = criticals);
      });
    });

    final dashAsync = ref.watch(dashboardProvider);
    final user = supabase.auth.currentUser;
    final lang = ref.watch(languageProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF0FDF4),
      appBar: AppBar(
        backgroundColor: const Color(0xFF065F46),
        foregroundColor: Colors.white,
        elevation: 0,
        titleSpacing: 16,
        title: const Text('MermaOps',
            style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -0.4, fontSize: 18)),
        actions: [
          TextButton(
            onPressed: () => ref.read(languageProvider.notifier).toggle(),
            child: Text(lang == 'es' ? 'EN' : 'ES',
                style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w700, fontSize: 13)),
          ),
          IconButton(
            icon: const Icon(Icons.refresh_outlined, color: Colors.white),
            tooltip: 'Actualizar',
            onPressed: () {
              ref.invalidate(dashboardProvider);
              ref.invalidate(_predictionsProvider);
              ref.invalidate(_comparisonProvider);
            },
          ),
          IconButton(
            icon: const Icon(Icons.person_outline, color: Colors.white),
            onPressed: () => context.go('/profile'),
          ),
        ],
      ),
      body: dashAsync.when(
        loading: () => const ShimmerKpiGrid(),
        error: (e, _) => _OfflineDashboard(error: e, ref: ref, userEmail: user?.email),
        data: (data) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(dashboardProvider);
            ref.invalidate(_predictionsProvider);
            ref.invalidate(_comparisonProvider);
            await Future.delayed(const Duration(milliseconds: 800));
          },
          child: _DashboardBody(data: data, userEmail: user?.email, ref: ref),
        ),
      ),
    );
  }
}

// ── Offline dashboard — muestra caché con banner cuando no hay internet ────────

class _OfflineDashboard extends StatefulWidget {
  final Object error;
  final WidgetRef ref;
  final String? userEmail;
  const _OfflineDashboard({required this.error, required this.ref, this.userEmail});

  @override
  State<_OfflineDashboard> createState() => _OfflineDashboardState();
}

class _OfflineDashboardState extends State<_OfflineDashboard> {
  Map<String, dynamic>? _cached;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadCache();
  }

  Future<void> _loadCache() async {
    final data = await _loadDashCache();
    if (mounted) setState(() { _cached = data; _loading = false; });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const SafeArea(child: ShimmerKpiGrid());

    final cached = _cached;
    if (cached == null) {
      // Sin caché: pantalla de error clásica
      return SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Container(
                width: 80, height: 80,
                decoration: BoxDecoration(color: const Color(0xFFFEF2F2), borderRadius: BorderRadius.circular(24)),
                child: const Icon(Icons.wifi_off_rounded, size: 40, color: Color(0xFFEF4444)),
              ),
              const SizedBox(height: 20),
              const Text('Sin conexión', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
              const SizedBox(height: 8),
              Text(friendlyError(widget.error), textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, color: Color(0xFF6B7280))),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: () => widget.ref.invalidate(dashboardProvider),
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Reintentar'),
              ),
            ]),
          ),
        ),
      );
    }

    // Con caché: mostrar datos antiguos + banner de aviso
    final cachedAt = cached['_cached_at'] as int? ?? 0;
    final age = DateTime.now().difference(DateTime.fromMillisecondsSinceEpoch(cachedAt));
    final ageLabel = age.inMinutes < 60
        ? 'hace ${age.inMinutes} min'
        : age.inHours < 24
            ? 'hace ${age.inHours}h'
            : 'hace ${age.inDays}d';

    return Column(children: [
      // Banner offline
      Material(
        color: const Color(0xFFFEF3C7),
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(children: [
              const Icon(Icons.wifi_off, size: 16, color: Color(0xFF92400E)),
              const SizedBox(width: 8),
              Expanded(child: Text('Sin conexión · datos $ageLabel', style: const TextStyle(fontSize: 12, color: Color(0xFF92400E), fontWeight: FontWeight.w600))),
              TextButton(
                onPressed: () => widget.ref.invalidate(dashboardProvider),
                style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 8), minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                child: const Text('Reintentar', style: TextStyle(fontSize: 12, color: Color(0xFF92400E))),
              ),
            ]),
          ),
        ),
      ),
      Expanded(
        child: RefreshIndicator(
          onRefresh: () async => widget.ref.invalidate(dashboardProvider),
          child: _DashboardBody(data: cached, userEmail: widget.userEmail, ref: widget.ref),
        ),
      ),
    ]);
  }
}

// ── Body (Stateful for animations) ───────────────────────────────────────────

class _DashboardBody extends StatefulWidget {
  final Map<String, dynamic> data;
  final String? userEmail;
  final WidgetRef ref;

  const _DashboardBody(
      {required this.data, this.userEmail, required this.ref});

  @override
  State<_DashboardBody> createState() => _DashboardBodyState();
}

class _DashboardBodyState extends State<_DashboardBody>
    with TickerProviderStateMixin {
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      duration: const Duration(milliseconds: 1600),
      vsync: this,
    )..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.5, end: 1.0).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  Color _headerColor(int critical) {
    if (critical >= 3) return const Color(0xFFDC2626);
    if (critical >= 1) return const Color(0xFFD97706);
    return const Color(0xFF059669);
  }

  @override
  Widget build(BuildContext context) {
    final pending = widget.data['pending_count'] as int? ?? 0;
    final critical = widget.data['critical_count'] as int? ?? 0;
    final high = widget.data['high_count'] as int? ?? 0;
    final valueAtRisk = (widget.data['value_at_risk'] as double? ?? 0);
    final expiring = widget.data['expiring_count'] as int? ?? 0;
    final brief = widget.data['brief'] as Map<String, dynamic>?;
    final merma7d =
        List<Map<String, dynamic>>.from(widget.data['merma_7d'] as List? ?? []);
    final donationQty = widget.data['donation_qty'] as int? ?? 0;
    final donationValue = widget.data['donation_value'] as double? ?? 0;
    final mostCriticalBatch =
        widget.data['most_critical_batch'] as Map<String, dynamic>?;
    final expiringToday = List<Map<String, dynamic>>.from(
        widget.data['expiring_today'] as List? ?? []);
    final completedToday = widget.data['completed_today'] as int? ?? 0;
    final predictiveAlerts = List<Map<String, dynamic>>.from(
        widget.data['predictive_alerts'] as List? ?? []);
    final name = widget.userEmail?.split('@').first ?? 'encargado';
    final headerBg = _headerColor(critical);
    final ref = widget.ref;

    final isWide = MediaQuery.of(context).size.width > 700;
    return ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
          children: [
                  // ── Status hero card ──────────────────────────────────────
                  _HeroBackground(
                    name: name,
                    critical: critical,
                    pending: pending,
                    pulseAnim: _pulseAnim,
                    headerBg: headerBg,
                  ),
                  const SizedBox(height: 16),
                  // KPI grid — 4 columnas en wide, 2x2 en móvil
                  Builder(builder: (ctx) {
                    if (isWide) {
                      return Row(children: [
                        Expanded(child: _KpiCard(label: tr(ref, 'pending_actions'), value: pending, icon: Icons.task_alt_rounded, color: pending > 0 ? UrgencyColors.high : UrgencyColors.low, onTap: () => context.go('/actions'))),
                        const SizedBox(width: 12),
                        Expanded(child: _KpiCard(label: tr(ref, 'critical_now'), value: critical, icon: Icons.crisis_alert_rounded, color: critical > 0 ? UrgencyColors.critical : UrgencyColors.low, glow: critical > 0, onTap: () => context.go('/actions'))),
                        const SizedBox(width: 12),
                        Expanded(child: _KpiCard(label: tr(ref, 'value_at_risk'), value: null, valueStr: '${valueAtRisk.toStringAsFixed(0)} €', icon: Icons.euro_rounded, color: valueAtRisk > 50 ? UrgencyColors.high : UrgencyColors.low, onTap: () => context.go('/reports'))),
                        const SizedBox(width: 12),
                        Expanded(child: _KpiCard(label: tr(ref, 'expiring_7d'), value: expiring, icon: Icons.schedule_rounded, color: UrgencyColors.medium, onTap: () => context.go('/map'))),
                      ]);
                    }
                    return Column(children: [
                      Row(children: [
                        Expanded(child: _KpiCard(label: tr(ref, 'pending_actions'), value: pending, icon: Icons.task_alt_rounded, color: pending > 0 ? UrgencyColors.high : UrgencyColors.low, onTap: () => context.go('/actions'))),
                        const SizedBox(width: 12),
                        Expanded(child: _KpiCard(label: tr(ref, 'critical_now'), value: critical, icon: Icons.crisis_alert_rounded, color: critical > 0 ? UrgencyColors.critical : UrgencyColors.low, glow: critical > 0, onTap: () => context.go('/actions'))),
                      ]),
                      const SizedBox(height: 12),
                      Row(children: [
                        Expanded(child: _KpiCard(label: tr(ref, 'value_at_risk'), value: null, valueStr: '${valueAtRisk.toStringAsFixed(0)} €', icon: Icons.euro_rounded, color: valueAtRisk > 50 ? UrgencyColors.high : UrgencyColors.low, onTap: () => context.go('/reports'))),
                        const SizedBox(width: 12),
                        Expanded(child: _KpiCard(label: tr(ref, 'expiring_7d'), value: expiring, icon: Icons.schedule_rounded, color: UrgencyColors.medium, onTap: () => context.go('/map'))),
                      ]),
                    ]);
                  }),
                  const SizedBox(height: 16),

                  // Weather card — tiempo real por ubicación del super
                  _WeatherCard(ref: widget.ref),
                  const SizedBox(height: 20),

                  // Urgency donut + legend
                  if (pending > 0) ...[
                    _UrgencySection(
                        total: pending, critical: critical, high: high),
                    const SizedBox(height: 20),
                  ],

                  // Critical spotlight card
                  if (critical > 0 && mostCriticalBatch != null) ...[
                    _CriticalSpotlight(batch: mostCriticalBatch),
                    const SizedBox(height: 20),
                  ],

                  // Today's progress bar
                  if (completedToday > 0 || pending > 0) ...[
                    _TodayProgressCard(
                        completed: completedToday, pending: pending),
                    const SizedBox(height: 20),
                  ],

                  // Predictive alerts — lotes sin acción que caducan pronto
                  if (predictiveAlerts.isNotEmpty) ...[
                    _PredictiveAlertsCard(alerts: predictiveAlerts),
                    const SizedBox(height: 16),
                  ],

                  // Expiring today/tomorrow mini-list
                  if (expiringToday.isNotEmpty) ...[
                    _ExpiringTodayCard(batches: expiringToday),
                    const SizedBox(height: 20),
                  ],

                  // Quick actions
                  const Text(
                    'Acciones rápidas',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF374151),
                      letterSpacing: -0.2,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: _QuickAction(
                          icon: Icons.qr_code_scanner_rounded,
                          label: tr(ref, 'scan_product'),
                          color: const Color(0xFF059669),
                          onTap: () => context.go('/scan'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _QuickAction(
                          icon: Icons.map_outlined,
                          label: tr(ref, 'daily_route'),
                          color: const Color(0xFF3B82F6),
                          onTap: () => context.go('/map'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _QuickAction(
                          icon: Icons.bar_chart_rounded,
                          label: tr(ref, 'nav_reports'),
                          color: const Color(0xFF8B5CF6),
                          onTap: () => context.go('/reports'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _QuickAction(
                          icon: Icons.auto_awesome_rounded,
                          label: tr(ref, 'generate_brief'),
                          color: const Color(0xFFF59E0B),
                          onTap: () => _runBrief(context, ref),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Merma area chart
                  if (merma7d.isNotEmpty) ...[
                    _MermaAreaCard(logs: merma7d),
                    const SizedBox(height: 20),
                  ],

                  // Donation impact
                  if (donationQty > 0) ...[
                    _DonationImpactCard(qty: donationQty, value: donationValue),
                    const SizedBox(height: 20),
                  ],

                  // Stores comparison
                  const _StoresComparisonCard(),
                  const SizedBox(height: 20),

                  // Brief — Kuine branded
                  if (brief != null)
                    _BriefCard(brief: brief, context: context)
                  else
                    _NoBriefCard(),
                  const SizedBox(height: 16),

                  // Daily progress bar
                  _DailyProgressBar(
                    completed: widget.data['completed_today'] as int? ?? 0,
                    pending: widget.data['pending_count'] as int? ?? 0,
                  ),

                  // Predictive radar
                  const _PredictionsCard(),

                  // ESG mini-card
                  _EsgMiniCard(dash: widget.data),
          ],
        );
  }

  void _runBrief(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      const SnackBar(
        content: Row(children: [
          SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
          SizedBox(width: 12),
          Expanded(child: Text('Kuine analizando… puede tardar 60–90 segundos')),
        ]),
        duration: Duration(seconds: 15),
        backgroundColor: Color(0xFF7C3AED),
      ),
    );

    try {
      final result = await api.runBrief();
      messenger.hideCurrentSnackBar();
      // El endpoint síncrono devuelve {"brief": "..."} directamente
      final briefText = result['brief'] as String? ?? '';
      ref.invalidate(dashboardProvider);
      if (briefText.isNotEmpty) {
        messenger.showSnackBar(const SnackBar(
            content: Text('Brief de Kuine generado. Dashboard actualizado.'),
            backgroundColor: Color(0xFF059669),
            duration: Duration(seconds: 4)));
      } else {
        // Si el brief ya existía hoy, también está bien
        messenger.showSnackBar(const SnackBar(
            content: Text('Dashboard actualizado con el último brief de Kuine.'),
            backgroundColor: Color(0xFF059669),
            duration: Duration(seconds: 4)));
      }
    } catch (e) {
      messenger.hideCurrentSnackBar();
      final errMsg = e.toString().contains('TimeoutException')
          ? 'Kuine tardó demasiado. Inténtalo de nuevo o usa "make brief" en terminal.'
          : friendlyError(e);
      messenger.showSnackBar(SnackBar(
          content: Text(errMsg),
          backgroundColor: const Color(0xFFEF4444),
          duration: const Duration(seconds: 6)));
    }
  }
}

// ── Hero Background ───────────────────────────────────────────────────────────

class _HeroBackground extends StatelessWidget {
  final String name;
  final int critical;
  final int pending;
  final Animation<double> pulseAnim;
  final Color headerBg;

  const _HeroBackground({
    required this.name,
    required this.critical,
    required this.pending,
    required this.pulseAnim,
    required this.headerBg,
  });

  String _statusLabel() {
    if (critical >= 3) return 'ALERTA — $critical críticos';
    if (critical >= 1) return '$critical crítico${critical > 1 ? 's' : ''} · $pending pendientes';
    if (pending > 0) return '$pending acciones pendientes';
    return 'Todo bajo control';
  }

  String _dateLabel() {
    final now = DateTime.now();
    const w = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
    const m = ['','enero','febrero','marzo','abril','mayo','junio',
        'julio','agosto','septiembre','octubre','noviembre','diciembre'];
    return '${w[now.weekday - 1]}, ${now.day} de ${m[now.month]}';
  }

  @override
  Widget build(BuildContext context) {
    final isDanger = critical >= 3;
    final isWarn = critical >= 1;
    final badgeColor = isDanger
        ? const Color(0xFFDC2626)
        : isWarn
            ? const Color(0xFFD97706)
            : Colors.white.withValues(alpha: 0.2);

    return Container(
      decoration: BoxDecoration(
        gradient: const _SafeGradient(
          colors: [Color(0xFF065F46), Color(0xFF047857)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF065F46).withValues(alpha: 0.4),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          // Kuine monitoring
          AnimatedBuilder(
            animation: pulseAnim,
            builder: (_, __) => Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: pulseAnim.value),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.white.withValues(alpha: pulseAnim.value * 0.5),
                        blurRadius: 6,
                        spreadRadius: 2,
                      )
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                const Text(
                  'KUINE MONITORIZANDO',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Hola, $name',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 26,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.8,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            _dateLabel(),
            style: const TextStyle(color: Colors.white70, fontSize: 12),
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: badgeColor,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              _statusLabel(),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ── KPI Card with animated counter ───────────────────────────────────────────

class _KpiCard extends StatelessWidget {
  final String label;
  final int? value;
  final String? valueStr;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;
  final bool glow;

  const _KpiCard({
    required this.label,
    this.value,
    this.valueStr,
    required this.icon,
    required this.color,
    this.onTap,
    this.glow = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: glow ? 0.35 : 0.12),
              blurRadius: glow ? 20 : 10,
              spreadRadius: glow ? 2 : 0,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: IntrinsicHeight(
          child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: 4,
              decoration: BoxDecoration(
                color: color,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  bottomLeft: Radius.circular(16),
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 14, 8, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(9),
                      ),
                      child: Icon(icon, color: color, size: 17),
                    ),
                    const SizedBox(height: 8),
                    if (value != null)
                      TweenAnimationBuilder<double>(
                        tween: Tween<double>(begin: 0.0, end: (value ?? 0).toDouble()),
                        duration: const Duration(milliseconds: 900),
                        curve: Curves.easeOut,
                        builder: (_, v, __) => Text(
                          v.toInt().toString(),
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.w900,
                            color: color,
                            letterSpacing: -1,
                          ),
                        ),
                      )
                    else
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: Alignment.centerLeft,
                        child: Text(
                          valueStr ?? '—',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w900,
                            color: color,
                            letterSpacing: -1,
                          ),
                        ),
                      ),
                    const SizedBox(height: 1),
                    Text(
                      label,
                      style: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFF6B7280),
                        height: 1.3,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
        ),
      ),
    );
  }
}

// ── Urgency Donut Section ─────────────────────────────────────────────────────

class _UrgencySection extends StatelessWidget {
  final int total;
  final int critical;
  final int high;

  const _UrgencySection(
      {required this.total, required this.critical, required this.high});

  @override
  Widget build(BuildContext context) {
    final normal = total - high;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 3))
        ],
      ),
      child: Row(
        children: [
          // Donut
          SizedBox(
            width: 100,
            height: 100,
            child: CustomPaint(
              painter: _DonutPainter(
                  critical: critical, high: high, total: total),
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TweenAnimationBuilder<double>(
                      tween: Tween<double>(begin: 0.0, end: total.toDouble()),
                      duration: const Duration(milliseconds: 900),
                      curve: Curves.easeOut,
                      builder: (_, v, __) => Text(
                        v.toInt().toString(),
                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFF111827),
                          letterSpacing: -1,
                        ),
                      ),
                    ),
                    Text(
                      total == 1 ? 'acción' : 'acciones',
                      style: const TextStyle(
                          fontSize: 9, color: Color(0xFF6B7280)),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),
          // Legend
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Distribución de urgencia',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF374151)),
                ),
                const SizedBox(height: 10),
                _LegendRow(
                    color: const Color(0xFFEF4444),
                    label: 'Crítico',
                    count: critical,
                    total: total),
                const SizedBox(height: 6),
                _LegendRow(
                    color: const Color(0xFFF59E0B),
                    label: 'Alto',
                    count: high - critical,
                    total: total),
                const SizedBox(height: 6),
                _LegendRow(
                    color: const Color(0xFF3B82F6),
                    label: 'Normal',
                    count: normal,
                    total: total),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LegendRow extends StatelessWidget {
  final Color color;
  final String label;
  final int count;
  final int total;

  const _LegendRow(
      {required this.color,
      required this.label,
      required this.count,
      required this.total});

  @override
  Widget build(BuildContext context) {
    final pct = total > 0 ? count / total : 0.0;
    return Row(
      children: [
        Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        SizedBox(
          width: 44,
          child: Text(label,
              style: const TextStyle(fontSize: 11, color: Color(0xFF374151))),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: 0.0, end: pct),
              duration: const Duration(milliseconds: 900),
              curve: Curves.easeOut,
              builder: (_, v, __) => LinearProgressIndicator(
                value: v,
                minHeight: 5,
                backgroundColor: color.withValues(alpha: 0.15),
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            ),
          ),
        ),
        const SizedBox(width: 6),
        Text('$count',
            style: TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, color: color)),
      ],
    );
  }
}

class _DonutPainter extends CustomPainter {
  final int critical;
  final int high;
  final int total;

  _DonutPainter({required this.critical, required this.high, required this.total});

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty || size.width < 16) return;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 8;
    const sw = 13.0;

    final bg = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..color = const Color(0xFFF3F4F6);
    canvas.drawCircle(center, radius, bg);

    if (total == 0) return;

    double start = -pi / 2;
    const gap = 0.08;

    for (final (count, color) in [
      (critical, const Color(0xFFEF4444)),
      (high - critical, const Color(0xFFF59E0B)),
      (total - high, const Color(0xFF3B82F6)),
    ]) {
      if (count <= 0) continue;
      final sweep = (count / total) * 2 * pi - gap;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start + gap / 2,
        sweep,
        false,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = sw
          ..color = color
          ..strokeCap = StrokeCap.round,
      );
      start += sweep + gap;
    }
  }

  @override
  bool shouldRepaint(_DonutPainter old) =>
      old.critical != critical || old.high != high || old.total != total;
}

// ── Critical Spotlight ────────────────────────────────────────────────────────

class _CriticalSpotlight extends StatelessWidget {
  final Map<String, dynamic> batch;
  const _CriticalSpotlight({required this.batch});

  @override
  Widget build(BuildContext context) {
    final productName = (batch['products'] as Map?)?['name'] as String? ??
        'Producto crítico';
    final expiry = batch['expiry_date'] as String? ?? '';
    final qty = (batch['quantity'] as num?)?.toInt() ?? 0;

    int daysLeft = 0;
    if (expiry.isNotEmpty) {
      try {
        final exp = DateTime.parse(expiry);
        daysLeft = exp.difference(DateTime.now()).inDays;
      } catch (_) {}
    }

    final urgencyText = daysLeft <= 0
        ? 'CADUCADO HOY'
        : daysLeft == 1
            ? 'Caduca mañana'
            : 'Caduca en $daysLeft días';

    return GestureDetector(
      onTap: () => context.push('/actions'),
      child: Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const _SafeGradient(
          colors: [Color(0xFFDC2626), Color(0xFFEF4444)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFEF4444).withValues(alpha: 0.35),
            blurRadius: 18,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.warning_amber_rounded,
                color: Colors.white, size: 28),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('MÁS URGENTE AHORA',
                    style: TextStyle(
                        color: Colors.white70,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.8)),
                const SizedBox(height: 3),
                Text(
                  productName,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '$urgencyText · $qty unidades',
                  style: const TextStyle(
                      color: Colors.white70, fontSize: 12),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.arrow_forward_rounded,
                color: Colors.white, size: 18),
          ),
        ],
      ),
    ),
    );
  }
}
// ── Merma Area Card ───────────────────────────────────────────────────────────

class _MermaAreaCard extends StatelessWidget {
  final List<Map<String, dynamic>> logs;
  const _MermaAreaCard({required this.logs});

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final days = List.generate(7, (i) => now.subtract(Duration(days: 6 - i)));

    final Map<String, double> byDate = {};
    for (final log in logs) {
      final date = log['date'] as String? ?? '';
      byDate[date] = (byDate[date] ?? 0) +
          ((log['value_lost'] as num?)?.toDouble() ?? 0);
    }

    final values = days
        .map((d) => byDate[d.toIso8601String().substring(0, 10)] ?? 0.0)
        .toList();
    final total7d = values.fold(0.0, (a, b) => a + b);
    final labels = days.map((d) {
      const l = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
      return l[d.weekday - 1];
    }).toList();

    // trend
    final last3 =
        values.sublist(4).fold(0.0, (a, b) => a + b) / 3;
    final first4 =
        values.sublist(0, 4).fold(0.0, (a, b) => a + b) / 4;
    final trending = last3 > first4 + 0.5;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 3))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: const Color(0xFFFEE2E2),
                  borderRadius: BorderRadius.circular(9),
                ),
                child: const Icon(Icons.show_chart_rounded,
                    color: Color(0xFFEF4444), size: 17),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text('Merma — últimos 7 días',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF111827))),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${total7d.toStringAsFixed(2)} €',
                    style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFFEF4444)),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                          trending
                              ? Icons.trending_up_rounded
                              : Icons.trending_down_rounded,
                          size: 12,
                          color: trending
                              ? const Color(0xFFEF4444)
                              : const Color(0xFF059669)),
                      const SizedBox(width: 2),
                      Text(
                        trending ? 'Subiendo' : 'Bajando',
                        style: TextStyle(
                            fontSize: 10,
                            color: trending
                                ? const Color(0xFFEF4444)
                                : const Color(0xFF059669),
                            fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 90,
            child: CustomPaint(
              painter: _AreaChartPainter(
                  values: values, color: const Color(0xFFEF4444)),
              child: Padding(
                padding: const EdgeInsets.only(top: 74),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: labels
                      .map((l) => Text(l,
                          style: const TextStyle(
                              fontSize: 10, color: Color(0xFF9CA3AF))))
                      .toList(),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AreaChartPainter extends CustomPainter {
  final List<double> values;
  final Color color;

  _AreaChartPainter({required this.values, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;
    if (size.isEmpty || size.width <= 0 || size.height <= 18) return;
    final maxV = values.reduce((a, b) => a > b ? a : b);
    if (maxV == 0) return;

    final h = size.height - 18;
    final w = size.width;
    final step = w / (values.length - 1);

    final pts = List.generate(
        values.length,
        (i) => Offset(i * step,
            h - (values[i] / maxV) * h * 0.88 + 4));

    // Gradient fill
    final fill = Path()..moveTo(0, h);
    fill.lineTo(pts[0].dx, pts[0].dy);
    for (int i = 1; i < pts.length; i++) {
      final c1 = Offset((pts[i - 1].dx + pts[i].dx) / 2, pts[i - 1].dy);
      final c2 = Offset((pts[i - 1].dx + pts[i].dx) / 2, pts[i].dy);
      fill.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, pts[i].dx, pts[i].dy);
    }
    fill.lineTo(w, h);
    fill.close();

    canvas.drawPath(
        fill,
        Paint()
          ..shader = LinearGradient(
            colors: [color.withValues(alpha: 0.3), color.withValues(alpha: 0)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ).createShader(Rect.fromLTWH(0, 0, w, h)));

    // Line
    final line = Path()..moveTo(pts[0].dx, pts[0].dy);
    for (int i = 1; i < pts.length; i++) {
      final c1 = Offset((pts[i - 1].dx + pts[i].dx) / 2, pts[i - 1].dy);
      final c2 = Offset((pts[i - 1].dx + pts[i].dx) / 2, pts[i].dy);
      line.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, pts[i].dx, pts[i].dy);
    }
    canvas.drawPath(
        line,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5
          ..strokeCap = StrokeCap.round);

    // End dot
    canvas.drawCircle(pts.last, 5, Paint()..color = color);
    canvas.drawCircle(pts.last, 3.5, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_AreaChartPainter old) =>
      old.values != values || old.color != color;
}

// ── Quick Action ──────────────────────────────────────────────────────────────

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _QuickAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 13, horizontal: 4),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(
                color: color.withValues(alpha: 0.18),
                blurRadius: 8,
                offset: const Offset(0, 3))
          ],
          border: Border.all(color: color.withValues(alpha: 0.12)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                  color: color, borderRadius: BorderRadius.circular(12)),
              child: Icon(icon, color: Colors.white, size: 22),
            ),
            const SizedBox(height: 7),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 10,
                color: color,
                fontWeight: FontWeight.w700,
                height: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Donation Impact ───────────────────────────────────────────────────────────

class _DonationImpactCard extends StatelessWidget {
  final int qty;
  final double value;
  const _DonationImpactCard({required this.qty, required this.value});

  @override
  Widget build(BuildContext context) {
    final kg = (qty * 0.35).toStringAsFixed(1);
    final co2 = (qty * 0.5).toStringAsFixed(1);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const _SafeGradient(
          colors: [Color(0xFF065F46), Color(0xFF059669)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
              color: const Color(0xFF059669).withValues(alpha: 0.35),
              blurRadius: 16,
              offset: const Offset(0, 6))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.volunteer_activism_rounded,
                color: Colors.white70, size: 16),
            const SizedBox(width: 6),
            const Text('Impacto social — últimos 30 días',
                style: TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w600)),
          ]),
          const SizedBox(height: 14),
          IntrinsicHeight(
            child: Row(
              children: [
                _ImpactCol('$qty', 'unidades\ndonadas'),
                VerticalDivider(
                    color: Colors.white.withValues(alpha: 0.25), width: 32),
                _ImpactCol('$kg kg', 'merma\nevitada'),
                VerticalDivider(
                    color: Colors.white.withValues(alpha: 0.25), width: 32),
                _ImpactCol('${value.toStringAsFixed(0)} €', 'valor\ndonado'),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(8)),
            child: Text('♻  $co2 kg CO₂ evitados · Ley 49/2002 (35% deducción)',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

class _ImpactCol extends StatelessWidget {
  final String value;
  final String label;
  const _ImpactCol(this.value, this.label);

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w900)),
          const SizedBox(height: 2),
          Text(label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 10,
                  height: 1.3)),
        ],
      ),
    );
  }
}

// ── Stores Comparison ─────────────────────────────────────────────────────────

class _StoresComparisonCard extends ConsumerWidget {
  const _StoresComparisonCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_comparisonProvider);
    return async.when(
      loading: () => Container(
        height: 52,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE5E7EB)),
        ),
        child: const Row(children: [
          SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 10),
          Text('Cargando ranking…',
              style: TextStyle(fontSize: 13, color: Colors.grey)),
        ]),
      ),
      error: (_, __) => const SizedBox.shrink(), // sección opcional, fallo silencioso aceptable
      data: (stores) {
        if (stores.isEmpty) return const SizedBox.shrink();
        final current = stores.firstWhere((s) => s['is_current'] == true,
            orElse: () => stores.first);
        final rank = current['rank'] as int? ?? 0;
        final total = stores.length;
        final maxMerma = stores.fold<double>(
            0,
            (m, s) =>
                ((s['merma_rate_pct'] as num?)?.toDouble() ?? 0) > m
                    ? (s['merma_rate_pct'] as num).toDouble()
                    : m);

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                  color: Colors.black.withValues(alpha: 0.05),
                  blurRadius: 10,
                  offset: const Offset(0, 3))
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.emoji_events_rounded,
                    color: Color(0xFFF59E0B), size: 18),
                const SizedBox(width: 8),
                const Expanded(
                    child: Text('Ranking de tiendas',
                        style: TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w700))),
                _RankBadge(rank: rank, total: total),
              ]),
              const SizedBox(height: 12),
              ...stores.map((s) {
                final name = s['store_name'] as String? ?? '';
                final merma =
                    (s['merma_rate_pct'] as num?)?.toDouble() ?? 0;
                final isCurrent = s['is_current'] == true;
                final r = s['rank'] as int? ?? 0;
                final ratio = maxMerma > 0 ? merma / maxMerma : 0.0;
                final medal = r == 1
                    ? '🥇'
                    : r == 2
                        ? '🥈'
                        : r == 3
                            ? '🥉'
                            : '$r.';

                return Padding(
                  padding: const EdgeInsets.only(bottom: 9),
                  child: Row(children: [
                    SizedBox(
                        width: 22,
                        child: Text(medal,
                            style: const TextStyle(fontSize: 12))),
                    const SizedBox(width: 4),
                    Expanded(
                        flex: 3,
                        child: Text(name,
                            style: TextStyle(
                                fontSize: 11,
                                fontWeight: isCurrent
                                    ? FontWeight.w700
                                    : FontWeight.normal,
                                color: isCurrent
                                    ? const Color(0xFF059669)
                                    : const Color(0xFF374151)),
                            overflow: TextOverflow.ellipsis)),
                    const SizedBox(width: 8),
                    Expanded(
                        flex: 4,
                        child: TweenAnimationBuilder<double>(
                          tween: Tween<double>(begin: 0.0, end: ratio),
                          duration: const Duration(milliseconds: 900),
                          curve: Curves.easeOut,
                          builder: (_, v, __) => ClipRRect(
                            borderRadius: BorderRadius.circular(3),
                            child: LinearProgressIndicator(
                              value: v,
                              minHeight: 7,
                              backgroundColor: const Color(0xFFF3F4F6),
                              valueColor: AlwaysStoppedAnimation<Color>(isCurrent
                                  ? const Color(0xFF059669)
                                  : const Color(0xFFD1D5DB)),
                            ),
                          ),
                        )),
                    const SizedBox(width: 8),
                    Text('${merma.toStringAsFixed(1)}%',
                        style: TextStyle(
                            fontSize: 11,
                            fontWeight: isCurrent
                                ? FontWeight.w700
                                : FontWeight.normal,
                            color: isCurrent
                                ? const Color(0xFF059669)
                                : const Color(0xFF9CA3AF))),
                  ]),
                );
              }),
              const SizedBox(height: 2),
              const Text('Tasa de merma sobre ventas — menor es mejor',
                  style: TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
            ],
          ),
        );
      },
    );
  }
}

class _RankBadge extends StatelessWidget {
  final int rank;
  final int total;
  const _RankBadge({required this.rank, required this.total});

  @override
  Widget build(BuildContext context) {
    final Color bg, fg;
    if (rank == 1) {
      bg = const Color(0xFFD1FAE5);
      fg = const Color(0xFF059669);
    } else if (rank <= 2) {
      bg = const Color(0xFFEFF6FF);
      fg = const Color(0xFF2563EB);
    } else {
      bg = const Color(0xFFFEE2E2);
      fg = const Color(0xFFDC2626);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text('Puesto $rank / $total',
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700, color: fg)),
    );
  }
}

// ── Today Progress Card ───────────────────────────────────────────────────────

class _TodayProgressCard extends StatelessWidget {
  final int completed;
  final int pending;
  const _TodayProgressCard({required this.completed, required this.pending});

  @override
  Widget build(BuildContext context) {
    final total = completed + pending;
    final pct = total > 0 ? completed / total : 0.0;
    final isDone = pending == 0 && completed > 0;
    final barColor = isDone
        ? const Color(0xFF059669)
        : pct >= 0.5
            ? const Color(0xFF3B82F6)
            : const Color(0xFFF59E0B);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 3))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: barColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(9),
              ),
              child: Icon(
                isDone ? Icons.check_circle_rounded : Icons.pending_actions_rounded,
                color: barColor,
                size: 17,
              ),
            ),
            const SizedBox(width: 10),
            const Expanded(
              child: Text('Progreso de hoy',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF111827))),
            ),
            Text(
              '$completed / $total',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  color: barColor),
            ),
          ]),
          const SizedBox(height: 12),
          TweenAnimationBuilder<double>(
            tween: Tween<double>(begin: 0.0, end: pct),
            duration: const Duration(milliseconds: 900),
            curve: Curves.easeOut,
            builder: (_, v, __) => ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: v,
                minHeight: 8,
                backgroundColor: barColor.withValues(alpha: 0.12),
                valueColor: AlwaysStoppedAnimation<Color>(barColor),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            isDone
                ? '¡Todo completado! La tienda está al día.'
                : '$pending acciones pendientes · $completed completadas hoy',
            style: TextStyle(
                fontSize: 11,
                color: isDone ? const Color(0xFF059669) : const Color(0xFF6B7280),
                fontWeight: isDone ? FontWeight.w600 : FontWeight.normal),
          ),
        ],
      ),
    );
  }
}

// ── Predictive Alerts Card ────────────────────────────────────────────────────
// Muestra productos sin acción asignada que caducan en <48h.
// "Inteligencia predictiva": Kuine ve ANTES de que el problema sea crítico.

class _PredictiveAlertsCard extends StatelessWidget {
  final List<Map<String, dynamic>> alerts;
  const _PredictiveAlertsCard({required this.alerts});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.4)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFF59E0B).withValues(alpha: 0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B).withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.auto_graph_rounded, size: 12, color: Color(0xFFF59E0B)),
                SizedBox(width: 4),
                Text('PREDICCIÓN', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: Color(0xFFF59E0B), letterSpacing: 0.5)),
              ]),
            ),
            const SizedBox(width: 8),
            const Text('Sin acción asignada — caducan pronto',
                style: TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
          ]),
          const SizedBox(height: 12),
          ...alerts.map((a) {
            final hoursLeft = a['hours_left'] as int? ?? 0;
            final product = a['product'] as String? ?? 'Producto';
            final qty = a['qty'] as int? ?? 0;
            final value = (a['value'] as num?)?.toDouble() ?? 0;
            final pasillo = a['pasillo'] ?? '?';

            final urgency = hoursLeft < 12
                ? const Color(0xFFEF4444)
                : const Color(0xFFF59E0B);
            final timeLabel = hoursLeft < 24
                ? '${hoursLeft}h'
                : '${(hoursLeft / 24).round()}d';

            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(children: [
                Container(
                  width: 40, height: 40,
                  decoration: BoxDecoration(
                    color: urgency.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: urgency.withValues(alpha: 0.3)),
                  ),
                  child: Center(
                    child: Text(timeLabel,
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: urgency)),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(product,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF111827)),
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    Text('Pasillo $pasillo · $qty uds · ${value.toStringAsFixed(0)}€',
                        style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
                  ]),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: urgency.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text('Sin acción',
                      style: TextStyle(fontSize: 10, color: urgency, fontWeight: FontWeight.w600)),
                ),
              ]),
            );
          }),
        ],
      ),
    );
  }
}

// ── Expiring Today Card ───────────────────────────────────────────────────────

class _ExpiringTodayCard extends StatelessWidget {
  final List<Map<String, dynamic>> batches;
  const _ExpiringTodayCard({required this.batches});

  @override
  Widget build(BuildContext context) {
    final today = DateTime.now().toIso8601String().substring(0, 10);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFFECACA)),
        boxShadow: [
          BoxShadow(
              color: const Color(0xFFEF4444).withValues(alpha: 0.08),
              blurRadius: 10,
              offset: const Offset(0, 3))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFFFEE2E2),
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(Icons.event_busy_rounded,
                  color: Color(0xFFDC2626), size: 17),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Caducan hoy o mañana (${batches.length})',
                style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF111827)),
              ),
            ),
          ]),
          const SizedBox(height: 12),
          ...batches.map((b) {
            final name =
                (b['products'] as Map?)?['name'] as String? ?? 'Producto';
            final pasillo =
                (b['products'] as Map?)?['pasillo'] as String? ?? '?';
            final qty = (b['quantity'] as num?)?.toInt() ?? 0;
            final expiry = b['expiry_date'] as String? ?? '';
            final isToday = expiry == today;
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(children: [
                Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    color: isToday
                        ? const Color(0xFFDC2626)
                        : const Color(0xFFF59E0B),
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(name,
                      style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF374151)),
                      overflow: TextOverflow.ellipsis),
                ),
                const SizedBox(width: 8),
                Text('P$pasillo',
                    style: const TextStyle(
                        fontSize: 11, color: Color(0xFF9CA3AF))),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: isToday
                        ? const Color(0xFFFEE2E2)
                        : const Color(0xFFFEF3C7),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    isToday ? 'HOY · $qty ud.' : 'MAÑANA · $qty ud.',
                    style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: isToday
                            ? const Color(0xFFDC2626)
                            : const Color(0xFFD97706)),
                  ),
                ),
              ]),
            );
          }),
        ],
      ),
    );
  }
}

// ── Brief Card ────────────────────────────────────────────────────────────────

class _BriefCard extends StatelessWidget {
  final Map<String, dynamic> brief;
  final BuildContext context;
  const _BriefCard({required this.brief, required this.context});

  @override
  Widget build(BuildContext ctx) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                gradient: const _SafeGradient(
                    colors: [Color(0xFF7C3AED), Color(0xFFA855F7)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight),
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(Icons.psychology_rounded,
                  color: Colors.white, size: 18),
            ),
            const SizedBox(width: 10),
            const Expanded(
                child: Text('Brief de Kuine',
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF111827)))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                  color: const Color(0xFFEDE9FE),
                  borderRadius: BorderRadius.circular(6)),
              child: Text(brief['date'] ?? '',
                  style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF7C3AED))),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFEDE9FE)),
            boxShadow: [
              BoxShadow(
                  color: const Color(0xFF7C3AED).withValues(alpha: 0.07),
                  blurRadius: 16,
                  offset: const Offset(0, 4))
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                brief['summary'] ?? 'Sin resumen disponible',
                style: const TextStyle(
                    fontSize: 13,
                    height: 1.65,
                    color: Color(0xFF374151)),
                maxLines: 8,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 14),
              GestureDetector(
                onTap: () => context.go('/reports'),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Ver informe completo',
                        style: TextStyle(
                            color: Color(0xFF7C3AED),
                            fontSize: 13,
                            fontWeight: FontWeight.w600)),
                    SizedBox(width: 4),
                    Icon(Icons.arrow_forward_rounded,
                        size: 14, color: Color(0xFF7C3AED)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _NoBriefCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFFDE68A)),
      ),
      child: Row(children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
              color: const Color(0xFFF59E0B).withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10)),
          child: const Icon(Icons.schedule_rounded,
              color: Color(0xFFD97706), size: 20),
        ),
        const SizedBox(width: 12),
        const Expanded(
          child: Text(
            'Brief no generado aún. Se genera a las 07:30 o puedes pedírselo a Chuwi en Telegram.',
            style: TextStyle(
                fontSize: 13, color: Color(0xFF92400E), height: 1.4),
          ),
        ),
      ]),
    );
  }
}

// ── Predictions Card ──────────────────────────────────────────────────────────

class _PredictionsCard extends ConsumerWidget {
  const _PredictionsCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(_predictionsProvider);
    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (data) {
        final preds = (data['predictions'] as List? ?? [])
            .cast<Map<String, dynamic>>()
            .where((p) => (p['risk_score'] as num? ?? 0) >= 40)
            .take(3)
            .toList();
        if (preds.isEmpty) return const SizedBox.shrink();
        final forecast = (data['weather_forecast'] as List? ?? []).cast<Map<String, dynamic>>();
        final events = (data['upcoming_events'] as List? ?? []).cast<String>();
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF1E3A5F), Color(0xFF1E40AF)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(18),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.radar_rounded, color: Colors.white, size: 22),
                const SizedBox(width: 8),
                const Expanded(child: Text('Radar Predictivo',
                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800))),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(8)),
                  child: const Text('7 días', style: TextStyle(color: Colors.white70, fontSize: 10)),
                ),
              ]),
              if (events.isNotEmpty) ...[
                const SizedBox(height: 8),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(children: events.take(3).map((e) => Container(
                    margin: const EdgeInsets.only(right: 6),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(color: const Color(0xFFFBBF24).withValues(alpha: 0.25), borderRadius: BorderRadius.circular(6)),
                    child: Text(e, style: const TextStyle(color: Color(0xFFFBBF24), fontSize: 10, fontWeight: FontWeight.w600)),
                  )).toList()),
                ),
              ],
              if (forecast.isNotEmpty) ...[
                const SizedBox(height: 10),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(children: forecast.take(5).map((f) {
                    final isHot = f['is_hot'] as bool? ?? false;
                    final isRainy = f['is_rainy'] as bool? ?? false;
                    final temp = (f['temp_max'] as num?)?.toDouble();
                    final rawDate = f['date'] as String? ?? '';
                    final date = rawDate.length >= 7 ? rawDate.substring(5) : rawDate;
                    return Container(
                      margin: const EdgeInsets.only(right: 6),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                      decoration: BoxDecoration(
                        color: isHot ? const Color(0xFFEF4444).withValues(alpha: 0.2)
                            : isRainy ? const Color(0xFF3B82F6).withValues(alpha: 0.2)
                            : Colors.white.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Column(children: [
                        Text(date, style: const TextStyle(color: Colors.white60, fontSize: 9)),
                        const SizedBox(height: 2),
                        Icon(isHot ? Icons.wb_sunny_rounded : isRainy ? Icons.water_drop_rounded : Icons.cloud_outlined,
                            color: isHot ? const Color(0xFFFBBF24) : isRainy ? const Color(0xFF93C5FD) : Colors.white60,
                            size: 16),
                        const SizedBox(height: 2),
                        Text(temp != null ? '${temp.toStringAsFixed(0)}°' : '?',
                            style: TextStyle(
                              color: isHot ? const Color(0xFFFBBF24) : Colors.white,
                              fontSize: 11, fontWeight: FontWeight.w700)),
                      ]),
                    );
                  }).toList()),
                ),
              ],
              const SizedBox(height: 12),
              ...preds.asMap().entries.map((entry) {
                final pred = entry.value;
                final name = pred['product_name'] as String? ?? '';
                final days = pred['days_until_expiry'] as int? ?? 0;
                final score = (pred['risk_score'] as num?)?.toInt() ?? 0;
                final action = pred['recommended_preemptive_action'] as String? ?? '';
                final scoreColor = score >= 70 ? const Color(0xFFEF4444)
                    : score >= 50 ? const Color(0xFFFBBF24)
                    : const Color(0xFF34D399);
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border(left: BorderSide(color: scoreColor, width: 3)),
                  ),
                  child: Row(children: [
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(name, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text(action.length > 55 ? '${action.substring(0, 55)}…' : action,
                          style: const TextStyle(color: Colors.white60, fontSize: 10)),
                    ])),
                    const SizedBox(width: 8),
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                        decoration: BoxDecoration(color: scoreColor, borderRadius: BorderRadius.circular(6)),
                        child: Text('$score/100', style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
                      ),
                      const SizedBox(height: 3),
                      Text('en $days días', style: const TextStyle(color: Colors.white54, fontSize: 9)),
                    ]),
                  ]),
                );
              }),
            ]),
          ),
        );
      },
    );
  }
}

// ── ESG Mini Card ─────────────────────────────────────────────────────────────

class _EsgMiniCard extends StatelessWidget {
  final Map<String, dynamic> dash;
  const _EsgMiniCard({required this.dash});

  @override
  Widget build(BuildContext context) {
    final donationValue = (dash['donation_value'] as num?)?.toDouble() ?? 0;
    final donationQty = (dash['donation_qty'] as num?)?.toInt() ?? 0;
    final completedToday = (dash['completed_today'] as num?)?.toInt() ?? 0;
    // Estimate CO2: ~2.5 kg CO2 per € food waste avoided
    final co2Kg = (donationValue * 2.5).clamp(0.0, 9999.0);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF0FDF4),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFBBF7D0), width: 1.5),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.eco_rounded, color: Color(0xFF059669), size: 20),
          SizedBox(width: 8),
          Text('Impacto ESG — últimos 30 días',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF065F46))),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          _EsgStat('${co2Kg.toStringAsFixed(0)} kg', 'CO₂ evitado', Icons.cloud_off_rounded, const Color(0xFF059669)),
          const SizedBox(width: 12),
          _EsgStat('${donationValue.toStringAsFixed(0)} €', 'Donado', Icons.volunteer_activism_rounded, const Color(0xFF3B82F6)),
          const SizedBox(width: 12),
          _EsgStat('$donationQty uds', 'Productos salvados', Icons.save_rounded, const Color(0xFFF59E0B)),
          const SizedBox(width: 12),
          _EsgStat('$completedToday hoy', 'Acciones', Icons.check_circle_rounded, const Color(0xFF8B5CF6)),
        ]),
      ]),
    );
  }
}

class _EsgStat extends StatelessWidget {
  final String value;
  final String label;
  final IconData icon;
  final Color color;
  const _EsgStat(this.value, this.label, this.icon, this.color);

  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(children: [
      Icon(icon, color: color, size: 20),
      const SizedBox(height: 4),
      Text(value, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12, color: color)),
      Text(label, style: const TextStyle(fontSize: 9, color: Colors.grey), textAlign: TextAlign.center),
    ]),
  );
}

// ── Daily Progress Bar ────────────────────────────────────────────────────────

class _DailyProgressBar extends StatelessWidget {
  final int completed;
  final int pending;
  const _DailyProgressBar({required this.completed, required this.pending});

  @override
  Widget build(BuildContext context) {
    final total = completed + pending;
    final pct = total == 0 ? 0.0 : completed / total;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.today_rounded, size: 16, color: Color(0xFF6B7280)),
          const SizedBox(width: 6),
          const Text('Progreso del día',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
          const Spacer(),
          Text('$completed / $total acciones',
              style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.w600,
                color: pct >= 1.0 ? const Color(0xFF059669) : const Color(0xFF6B7280),
              )),
        ]),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: pct,
            minHeight: 10,
            backgroundColor: const Color(0xFFE5E7EB),
            valueColor: AlwaysStoppedAnimation<Color>(
              pct >= 1.0 ? const Color(0xFF059669) : pct >= 0.5 ? const Color(0xFF3B82F6) : const Color(0xFFF59E0B),
            ),
          ),
        ),
        if (pct >= 1.0) ...[
          const SizedBox(height: 6),
          const Row(children: [
            Icon(Icons.check_circle_rounded, color: Color(0xFF059669), size: 14),
            SizedBox(width: 4),
            Text('¡Todo el trabajo de hoy completado!',
                style: TextStyle(fontSize: 11, color: Color(0xFF059669), fontWeight: FontWeight.w600)),
          ]),
        ],
      ]),
    );
  }
}

// ── Weather Card ──────────────────────────────────────────────────────────────

class _WeatherCard extends StatelessWidget {
  final WidgetRef ref;
  const _WeatherCard({required this.ref});

  static const _wCodes = {
    0: ('Despejado', Icons.wb_sunny_rounded),
    1: ('Casi despejado', Icons.wb_sunny_outlined),
    2: ('Parcialmente nublado', Icons.cloud_rounded),
    3: ('Nublado', Icons.cloud_rounded),
    45: ('Niebla', Icons.foggy),
    48: ('Niebla helada', Icons.foggy),
    51: ('Llovizna', Icons.grain_rounded),
    61: ('Lluvia leve', Icons.water_drop_outlined),
    63: ('Lluvia moderada', Icons.water_drop_rounded),
    65: ('Lluvia intensa', Icons.thunderstorm_outlined),
    71: ('Nevada leve', Icons.ac_unit_rounded),
    80: ('Chubascos', Icons.water_drop_outlined),
    95: ('Tormenta', Icons.thunderstorm_rounded),
  };

  (String, IconData) _wxInfo(int code) {
    if (_wCodes.containsKey(code)) return _wCodes[code]!;
    if (code <= 3) return ('Despejado', Icons.wb_sunny_rounded);
    if (code <= 48) return ('Nublado', Icons.cloud_rounded);
    if (code <= 67) return ('Lluvia', Icons.water_drop_rounded);
    if (code <= 77) return ('Nieve', Icons.ac_unit_rounded);
    return ('Tormenta', Icons.thunderstorm_rounded);
  }

  Color _wxColor(int code) {
    if (code <= 1) return const Color(0xFFF59E0B);
    if (code <= 3) return const Color(0xFF64748B);
    if (code <= 48) return const Color(0xFF94A3B8);
    if (code <= 77) return const Color(0xFF3B82F6);
    return const Color(0xFF7C3AED);
  }

  @override
  Widget build(BuildContext context) {
    final wx = ref.watch(_weatherProvider);
    return wx.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (data) {
        final city = data['city'] as String? ?? '';
        final current = data['current'] as Map<String, dynamic>?;
        final forecast = (data['forecast'] as List? ?? []).cast<Map<String, dynamic>>();
        if (current == null) return const SizedBox.shrink();

        final temp = (current['temp_max'] as num?)?.round() ?? 0;
        final code = (current['weather_code'] as num?)?.toInt() ?? 0;
        final precip = (current['precipitation_mm'] as num?)?.toDouble() ?? 0;
        final humidity = (current['relative_humidity_2m_max'] as num?)?.toInt();
        final (label, icon) = _wxInfo(code);
        final color = _wxColor(code);

        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [color.withValues(alpha: 0.12), color.withValues(alpha: 0.05)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: color.withValues(alpha: 0.25)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Icon(Icons.location_on_rounded, size: 13, color: color.withValues(alpha: 0.7)),
                const SizedBox(width: 3),
                Text(city, style: TextStyle(fontSize: 11, color: color.withValues(alpha: 0.8), fontWeight: FontWeight.w600)),
                const Spacer(),
                Text('Actualizado ahora', style: TextStyle(fontSize: 9, color: Colors.grey[500])),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Icon(icon, color: color, size: 36),
                const SizedBox(width: 12),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('$temp°C', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: color, height: 1.0)),
                  Text(label, style: TextStyle(fontSize: 12, color: color.withValues(alpha: 0.8), fontWeight: FontWeight.w500)),
                ]),
                const Spacer(),
                if (humidity != null) _WxPill(Icons.water_outlined, '$humidity%', color),
                const SizedBox(width: 6),
                if (precip > 0) _WxPill(Icons.umbrella_outlined, '${precip.toStringAsFixed(1)}mm', const Color(0xFF3B82F6)),
              ]),
              if (forecast.length > 1) ...[
                const SizedBox(height: 10),
                const Divider(height: 1),
                const SizedBox(height: 8),
                // 5-day mini forecast
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: forecast.skip(1).take(5).map((f) {
                    final d = f['date'] as String? ?? '';
                    final t2 = (f['temp_max'] as num?)?.round() ?? 0;
                    final c2 = (f['weather_code'] as num?)?.toInt() ?? 0;
                    final (_, ic2) = _wxInfo(c2);
                    final dayLabel = _dayLabel(d);
                    return Column(mainAxisSize: MainAxisSize.min, children: [
                      Text(dayLabel, style: const TextStyle(fontSize: 9, color: Colors.grey, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 3),
                      Icon(ic2, size: 16, color: _wxColor(c2)),
                      const SizedBox(height: 2),
                      Text('$t2°', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
                    ]);
                  }).toList(),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  String _dayLabel(String isoDate) {
    try {
      final d = DateTime.parse(isoDate);
      const days = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
      return days[d.weekday % 7];
    } catch (_) {
      return '';
    }
  }
}

class _WxPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  const _WxPill(this.icon, this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 11, color: color),
        const SizedBox(width: 3),
        Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
      ]),
    );
  }
}
