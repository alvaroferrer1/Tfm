import 'dart:math' show pi;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_service.dart';
import '../../core/l10n.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';

// ── Providers ─────────────────────────────────────────────────────────────────

final _comparisonProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getStoresComparison();
});

final dashboardProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final pending = await supabase
      .from('actions')
      .select('priority_score, action_type, urgency_level, batch_id')
      .eq('store_id', storeId)
      .eq('status', 'pending')
      .order('priority_score', ascending: false);

  final batches = await supabase
      .from('batches')
      .select('quantity, expiry_date, products(name, price)')
      .eq('store_id', storeId)
      .eq('status', 'active')
      .lte('expiry_date',
          DateTime.now().add(const Duration(days: 7)).toIso8601String().substring(0, 10))
      .order('expiry_date', ascending: true);

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
    final qty = (b['quantity'] as num?)?.toDouble() ?? 0;
    final price = ((b['products'] as Map?)?['price'] as num?)?.toDouble() ?? 0;
    valueAtRisk += qty * price;
    mostCritical ??= b; // first is soonest to expire
  }

  final pendingList = List<Map<String, dynamic>>.from(pending);
  final criticalCount =
      pendingList.where((a) => (a['priority_score'] as int? ?? 0) >= 85).length;
  final highCount =
      pendingList.where((a) => (a['priority_score'] as int? ?? 0) >= 60).length;

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

  return {
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
  };
});

// ── Screen ────────────────────────────────────────────────────────────────────

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashAsync = ref.watch(dashboardProvider);
    final user = supabase.auth.currentUser;

    return Scaffold(
      backgroundColor: const Color(0xFFF0FDF4),
      body: dashAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF2F2),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: const Icon(Icons.wifi_off_rounded,
                        size: 40, color: Color(0xFFEF4444)),
                  ),
                  const SizedBox(height: 20),
                  const Text('Sin conexión',
                      style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF111827))),
                  const SizedBox(height: 8),
                  Text('$e',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          fontSize: 13, color: Color(0xFF6B7280))),
                  const SizedBox(height: 24),
                  ElevatedButton.icon(
                    onPressed: () => ref.invalidate(dashboardProvider),
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Reintentar'),
                  ),
                ],
              ),
            ),
          ),
        ),
        data: (data) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(dashboardProvider),
          child: _DashboardBody(data: data, userEmail: user?.email, ref: ref),
        ),
      ),
    );
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
  late AnimationController _slideCtrl;
  late Animation<double> _pulseAnim;
  late Animation<Offset> _slideAnim;
  late Animation<double> _fadeAnim;

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

    _slideCtrl = AnimationController(
      duration: const Duration(milliseconds: 700),
      vsync: this,
    )..forward();
    _slideAnim = Tween<Offset>(begin: const Offset(0, 0.06), end: Offset.zero)
        .animate(CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut));
    _fadeAnim = CurvedAnimation(parent: _slideCtrl, curve: Curves.easeOut);
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _slideCtrl.dispose();
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
    final name = widget.userEmail?.split('@').first ?? 'encargado';
    final headerBg = _headerColor(critical);
    final ref = widget.ref;

    return FadeTransition(
      opacity: _fadeAnim,
      child: SlideTransition(
        position: _slideAnim,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // ── Sliver Hero Header ──────────────────────────────────────────
            SliverAppBar(
              expandedHeight: 220,
              pinned: true,
              stretch: true,
              backgroundColor: headerBg,
              foregroundColor: Colors.white,
              elevation: 0,
              flexibleSpace: FlexibleSpaceBar(
                titlePadding:
                    const EdgeInsets.only(left: 16, bottom: 12, right: 120),
                title: Text(
                  'MermaOps',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.4,
                  ),
                ),
                stretchModes: const [StretchMode.zoomBackground],
                background: _HeroBackground(
                  name: name,
                  critical: critical,
                  pending: pending,
                  pulseAnim: _pulseAnim,
                  headerBg: headerBg,
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () =>
                      ref.read(languageProvider.notifier).toggle(),
                  child: Text(
                    ref.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 13),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.refresh_outlined),
                  color: Colors.white,
                  onPressed: () => ref.invalidate(dashboardProvider),
                ),
                IconButton(
                  icon: const Icon(Icons.person_outline),
                  color: Colors.white,
                  onPressed: () => context.go('/profile'),
                ),
              ],
            ),

            // ── Content ─────────────────────────────────────────────────────
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 20, 16, 40),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  // KPI grid
                  Row(
                    children: [
                      Expanded(
                        child: _KpiCard(
                          label: tr(ref, 'pending_actions'),
                          value: pending,
                          icon: Icons.task_alt_rounded,
                          color: pending > 0
                              ? UrgencyColors.high
                              : UrgencyColors.low,
                          onTap: () => context.go('/actions'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _KpiCard(
                          label: tr(ref, 'critical_now'),
                          value: critical,
                          icon: Icons.crisis_alert_rounded,
                          color: critical > 0
                              ? UrgencyColors.critical
                              : UrgencyColors.low,
                          glow: critical > 0,
                          onTap: () => context.go('/actions'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _KpiCard(
                          label: tr(ref, 'value_at_risk'),
                          value: null,
                          valueStr: '${valueAtRisk.toStringAsFixed(0)} €',
                          icon: Icons.euro_rounded,
                          color: valueAtRisk > 50
                              ? UrgencyColors.high
                              : UrgencyColors.low,
                          onTap: () => context.go('/reports'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _KpiCard(
                          label: tr(ref, 'expiring_7d'),
                          value: expiring,
                          icon: Icons.schedule_rounded,
                          color: UrgencyColors.medium,
                          onTap: () => context.go('/map'),
                        ),
                      ),
                    ],
                  ),
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
                ]),
              ),
            ),
          ],
        ),
      ),
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
        duration: Duration(seconds: 180),
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
          : 'Error generando brief: $e';
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

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: isDanger
              ? [const Color(0xFFB91C1C), const Color(0xFFDC2626)]
              : isWarn
                  ? [const Color(0xFFB45309), const Color(0xFFD97706)]
                  : [const Color(0xFF047857), const Color(0xFF059669)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      padding: EdgeInsets.fromLTRB(
          20, MediaQuery.of(context).padding.top + kToolbarHeight + 8, 20, 20),
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
              color: Colors.white.withValues(alpha: 0.2),
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
                        tween: Tween(begin: 0, end: value!.toDouble()),
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
                      tween: Tween(begin: 0, end: total.toDouble()),
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
              tween: Tween(begin: 0, end: pct),
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

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
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
        gradient: const LinearGradient(
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
      error: (_, __) => const SizedBox.shrink(),
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
                          tween: Tween(begin: 0, end: ratio),
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
                gradient: const LinearGradient(
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
