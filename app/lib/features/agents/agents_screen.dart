import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_service.dart';
import '../../core/supabase_client.dart';
import '../../core/user_role_provider.dart';

// provider accesible desde otros widgets
final agentStatusRefreshProvider = StateProvider<int>((ref) => 0);

// ── Providers ─────────────────────────────────────────────────────────────────

final _agentStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getAgentStatus();
});

final _agentActivityProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getAgentActivity();
});

final _agentConversationsProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getAgentConversations(limit: 10);
});

final _agentRunsProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getAgentRuns(limit: 15);
});

final _supervisorDecisionsProvider =
    FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getSupervisorDecisions(limit: 30);
});

// ── Agent metadata ────────────────────────────────────────────────────────────

const _agentIcons = <String, IconData>{
  'orchestrator': Icons.psychology_rounded,
  'conversational': Icons.chat_rounded,
  'evaluator': Icons.analytics_rounded,
  'validator': Icons.verified_user_rounded,
  'consensus': Icons.how_to_vote_rounded,
  'predictor': Icons.trending_up_rounded,
  'vision': Icons.remove_red_eye_rounded,
  'reporter': Icons.summarize_rounded,
  'notifier': Icons.notifications_active_rounded,
  'price': Icons.sell_rounded,
  'stock': Icons.inventory_2_rounded,
};

const _agentColors = <String, Color>{
  'orchestrator': Color(0xFF7C3AED),
  'conversational': Color(0xFF3B82F6),
  'evaluator': Color(0xFFF59E0B),
  'validator': Color(0xFFEF4444),
  'consensus': Color(0xFF0891B2),
  'predictor': Color(0xFF4F46E5),
  'vision': Color(0xFFEC4899),
  'reporter': Color(0xFF059669),
  'notifier': Color(0xFF10B981),
  'price': Color(0xFFF97316),
  'stock': Color(0xFF8B5CF6),
};

Color _agentColor(String type) =>
    _agentColors[type] ?? const Color(0xFF6B7280);
IconData _agentIcon(String type) =>
    _agentIcons[type] ?? Icons.memory_rounded;

// ── Screen ────────────────────────────────────────────────────────────────────

class AgentsScreen extends ConsumerWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return RoleGate(
      requiredRole: UserRole.manager,
      child: const _AgentsContent(),
    );
  }
}

class _AgentsContent extends ConsumerStatefulWidget {
  const _AgentsContent();

  @override
  ConsumerState<_AgentsContent> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends ConsumerState<_AgentsContent>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  void _refresh() {
    ref.invalidate(_agentStatusProvider);
    ref.invalidate(_agentActivityProvider);
    ref.invalidate(_agentConversationsProvider);
    ref.invalidate(_agentRunsProvider);
    ref.invalidate(_supervisorDecisionsProvider);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FB),
      appBar: AppBar(
        title: Row(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8)),
            child: const Icon(Icons.hub_rounded, color: Colors.white, size: 15),
          ),
          const SizedBox(width: 8),
          const Text('Red de Agentes'),
        ]),
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _refresh,
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          labelStyle:
              const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
          unselectedLabelStyle:
              const TextStyle(fontWeight: FontWeight.normal, fontSize: 13),
          indicatorWeight: 3,
          tabs: const [
            Tab(text: 'Red'),
            Tab(text: 'Conversaciones'),
            Tab(text: 'Runs Kuine'),
            Tab(text: 'Decisiones'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _NetworkTab(),
          _ConversationsTab(),
          _RunsTab(),
          _DecisionsTab(),
        ],
      ),
    );
  }
}

// ── Tab 1: Network ────────────────────────────────────────────────────────────

class _NetworkTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_NetworkTab> createState() => _NetworkTabState();
}

class _NetworkTabState extends ConsumerState<_NetworkTab>
    with TickerProviderStateMixin {
  late AnimationController _pulseCtrl;
  late AnimationController _flowCtrl;
  late Animation<double> _pulseAnim;
  late Animation<double> _flowAnim;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
        duration: const Duration(milliseconds: 1600), vsync: this)
      ..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.4, end: 1.0)
        .animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    _flowCtrl = AnimationController(
        duration: const Duration(seconds: 3), vsync: this)
      ..repeat();
    _flowAnim =
        CurvedAnimation(parent: _flowCtrl, curve: Curves.easeInOut);
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _flowCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(_agentStatusProvider);
    final activityAsync = ref.watch(_agentActivityProvider);

    return ListView(
      padding: const EdgeInsets.fromLTRB(0, 0, 0, 40),
      children: [
        // ── AI Pipeline Flow ────────────────────────────────────────────────
        _PipelineFlowCard(pulseAnim: _pulseAnim, flowAnim: _flowAnim),

        // ── System Health ───────────────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: statusAsync.when(
            data: (data) {
              final agents =
                  List<Map<String, dynamic>>.from(data['agents'] ?? []);
              final active =
                  agents.where((a) => a['status'] == 'active').length;
              return _SystemHealthCard(
                  active: active, total: agents.length, anim: _pulseAnim);
            },
            loading: () => _SystemHealthCard(
                active: 0, total: 11, anim: _pulseAnim, loading: true),
            error: (_, __) => const SizedBox.shrink(),
          ),
        ),

        // ── Activity ────────────────────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: activityAsync.when(
            data: (a) => _ActivityCard(activity: a),
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => _ErrorBanner(e.toString()),
          ),
        ),

        // ── Agent Hierarchy ─────────────────────────────────────────────────
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 0, 16, 10),
          child: Text('Jerarquía de agentes',
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF111827),
                  letterSpacing: -0.2)),
        ),

        statusAsync.when(
          data: (data) {
            final agents =
                List<Map<String, dynamic>>.from(data['agents'] ?? []);
            return _AgentHierarchy(agents: agents, pulseAnim: _pulseAnim);
          },
          loading: () => const Center(
              child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator())),
          error: (e, _) => Padding(
              padding: const EdgeInsets.all(16),
              child: _ErrorBanner(e.toString())),
        ),
      ],
    );
  }
}

// ── Pipeline Flow Card ────────────────────────────────────────────────────────

class _PipelineFlowCard extends StatelessWidget {
  final Animation<double> pulseAnim;
  final Animation<double> flowAnim;

  const _PipelineFlowCard(
      {required this.pulseAnim, required this.flowAnim});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0F0C29), Color(0xFF302B63), Color(0xFF24243E)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
              color: const Color(0xFF7C3AED).withValues(alpha: 0.3),
              blurRadius: 20,
              offset: const Offset(0, 8))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.hub_rounded, color: Colors.white70, size: 14),
            SizedBox(width: 6),
            Text('PIPELINE DE IA — TIEMPO REAL',
                style: TextStyle(
                    color: Colors.white54,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1)),
          ]),
          const SizedBox(height: 16),
          // Pipeline nodes
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _PipelineNode(
                  label: 'Encargado',
                  icon: Icons.person_rounded,
                  color: const Color(0xFF60A5FA),
                  anim: pulseAnim),
              _PipelineArrow(anim: flowAnim),
              _PipelineNode(
                  label: 'Chuwi',
                  icon: Icons.chat_rounded,
                  color: const Color(0xFF34D399),
                  anim: pulseAnim),
              _PipelineArrow(anim: flowAnim, delay: 0.33),
              _PipelineNode(
                  label: 'Kuine',
                  icon: Icons.psychology_rounded,
                  color: const Color(0xFFA78BFA),
                  anim: pulseAnim,
                  big: true),
              _PipelineArrow(anim: flowAnim, delay: 0.66),
              _SubagentStack(anim: pulseAnim),
            ],
          ),
          const SizedBox(height: 16),
          // Model tier labels
          Row(children: [
            _ModelTier(label: 'Claude Haiku 4.5', subtitle: 'Precio · Stock', color: const Color(0xFF0891B2)),
            const SizedBox(width: 8),
            _ModelTier(label: 'Claude Sonnet 4.6', subtitle: 'Evaluador · Validador +7', color: const Color(0xFF3B82F6)),
            const SizedBox(width: 8),
            _ModelTier(label: 'Claude Opus 4.7', subtitle: 'Kuine', color: const Color(0xFF7C3AED)),
          ]),
        ],
      ),
    );
  }
}

class _PipelineNode extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final Animation<double> anim;
  final bool big;

  const _PipelineNode({
    required this.label,
    required this.icon,
    required this.color,
    required this.anim,
    this.big = false,
  });

  @override
  Widget build(BuildContext context) {
    final size = big ? 52.0 : 40.0;
    return Column(
      children: [
        AnimatedBuilder(
          animation: anim,
          builder: (_, child) => Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(big ? 14 : 11),
              border: Border.all(
                  color: color.withValues(alpha: anim.value), width: big ? 2 : 1.5),
              boxShadow: [
                BoxShadow(
                    color: color.withValues(alpha: anim.value * 0.4),
                    blurRadius: big ? 16 : 10,
                    spreadRadius: big ? 3 : 1)
              ],
            ),
            child: Icon(icon, color: color, size: big ? 26 : 20),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          label,
          style: TextStyle(
              color: Colors.white70,
              fontSize: big ? 10 : 9,
              fontWeight: big ? FontWeight.w700 : FontWeight.normal),
        ),
      ],
    );
  }
}

class _PipelineArrow extends StatelessWidget {
  final Animation<double> anim;
  final double delay;

  const _PipelineArrow({required this.anim, this.delay = 0});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: anim,
      builder: (_, __) {
        final t = ((anim.value + delay) % 1.0);
        return SizedBox(
          width: 28,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(height: 1.5, color: Colors.white12),
              Positioned(
                left: t * 24,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    color: const Color(0xFFA78BFA),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                          color: const Color(0xFFA78BFA).withValues(alpha: 0.6),
                          blurRadius: 4)
                    ],
                  ),
                ),
              ),
              const Positioned(
                right: 0,
                child: Icon(Icons.arrow_right_rounded,
                    color: Colors.white24, size: 16),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SubagentStack extends StatelessWidget {
  final Animation<double> anim;
  const _SubagentStack({required this.anim});

  static const _colors = [
    Color(0xFFFBBF24),
    Color(0xFFEF4444),
    Color(0xFF0EA5E9),
    Color(0xFF10B981),
    Color(0xFFEC4899),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      SizedBox(
        width: 50,
        height: 40,
        child: Stack(
          children: List.generate(5, (i) {
            return Positioned(
              left: i * 6.0,
              child: AnimatedBuilder(
                animation: anim,
                builder: (_, __) => Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: _colors[i].withValues(alpha: 0.25),
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(
                        color: _colors[i].withValues(alpha: 0.6), width: 1.5),
                  ),
                  child: Icon(Icons.smart_toy_rounded,
                      color: _colors[i], size: 13),
                ),
              ),
            );
          }),
        ),
      ),
      const SizedBox(height: 6),
      const Text('9 agentes',
          style: TextStyle(color: Colors.white70, fontSize: 9)),
    ]);
  }
}

class _ModelTier extends StatelessWidget {
  final String label;
  final String subtitle;
  final Color color;

  const _ModelTier(
      {required this.label, required this.subtitle, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(
                    color: color, fontSize: 9, fontWeight: FontWeight.w700),
                overflow: TextOverflow.ellipsis),
            Text(subtitle,
                style: const TextStyle(color: Colors.white38, fontSize: 8),
                overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

// ── System Health Card ────────────────────────────────────────────────────────

class _SystemHealthCard extends StatelessWidget {
  final int active;
  final int total;
  final Animation<double> anim;
  final bool loading;

  const _SystemHealthCard({
    required this.active,
    required this.total,
    required this.anim,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    final allOk = !loading && active == total;
    final colors = allOk
        ? const [Color(0xFF047857), Color(0xFF059669)]
        : loading
            ? const [Color(0xFF374151), Color(0xFF4B5563)]
            : const [Color(0xFFB45309), Color(0xFFD97706)];

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient:
            LinearGradient(colors: colors, begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
              color: colors.first.withValues(alpha: 0.35),
              blurRadius: 18,
              offset: const Offset(0, 6))
        ],
      ),
      child: Row(children: [
        AnimatedBuilder(
          animation: anim,
          builder: (_, __) => Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.15 + anim.value * 0.1),
              borderRadius: BorderRadius.circular(14),
              boxShadow: [
                BoxShadow(
                    color: Colors.white.withValues(alpha: anim.value * 0.15),
                    blurRadius: 12,
                    spreadRadius: 2)
              ],
            ),
            child: const Icon(Icons.hub_rounded, color: Colors.white, size: 28),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                loading
                    ? 'Verificando sistema…'
                    : allOk
                        ? 'Sistema 100% operativo'
                        : '$active/$total activos',
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                    letterSpacing: -0.4),
              ),
              const SizedBox(height: 3),
              const Text('Opus 4.7 · Sonnet 4.6 · Haiku 4.5',
                  style: TextStyle(color: Colors.white70, fontSize: 12)),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(
            loading ? '…' : '$active/$total',
            style: const TextStyle(
                color: Colors.white, fontWeight: FontWeight.w900, fontSize: 20),
          ),
        ),
      ]),
    );
  }
}

// ── Activity Card ─────────────────────────────────────────────────────────────

class _ActivityCard extends StatelessWidget {
  final Map<String, dynamic> activity;
  const _ActivityCard({required this.activity});

  @override
  Widget build(BuildContext context) {
    final topTools = List<dynamic>.from(activity['top_tools'] ?? []);
    final intents = Map<String, dynamic>.from(activity['intent_breakdown'] ?? {});
    final kuine = activity['kuine_calls_24h'] ?? 0;
    final msgs = activity['messages_24h'] ?? 0;

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
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                  color: const Color(0xFFEFF6FF),
                  borderRadius: BorderRadius.circular(8)),
              child: const Icon(Icons.timeline_rounded,
                  color: Color(0xFF3B82F6), size: 16),
            ),
            const SizedBox(width: 8),
            const Text('Actividad — últimas 24h',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          ]),
          const SizedBox(height: 14),
          Row(children: [
            _StatBox(value: '$msgs', label: 'mensajes\nChuwi', color: const Color(0xFF3B82F6)),
            const SizedBox(width: 10),
            _StatBox(value: '$kuine', label: 'llamadas\nKuine', color: const Color(0xFF7C3AED)),
            if (topTools.isNotEmpty) ...[
              const SizedBox(width: 10),
              _StatBox(value: '${topTools.length}', label: 'tools\nusadas', color: const Color(0xFF059669)),
            ],
          ]),
          if (topTools.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 5,
              children: topTools.take(8).map((t) {
                final name = t is Map ? t['tool'] ?? '' : t.toString();
                final count = t is Map ? t['count'] : null;
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEFF6FF),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: const Color(0xFFBFDBFE)),
                  ),
                  child: Text(
                    '$name${count != null ? ' ·$count' : ''}',
                    style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF1D4ED8),
                        fontWeight: FontWeight.w500),
                  ),
                );
              }).toList(),
            ),
          ],
          if (intents.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 5,
              children: intents.entries
                  .map((e) => Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 7, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF3F4F6),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text('${e.key}: ${e.value}',
                            style: const TextStyle(
                                fontSize: 10, color: Color(0xFF374151))),
                      ))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _StatBox extends StatelessWidget {
  final String value;
  final String label;
  final Color color;
  const _StatBox({required this.value, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.07),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Column(children: [
          Text(value,
              style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w900,
                  color: color,
                  letterSpacing: -0.5)),
          const SizedBox(height: 2),
          Text(label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 10, color: Color(0xFF6B7280), height: 1.3)),
        ]),
      ),
    );
  }
}

// ── Agent Hierarchy ───────────────────────────────────────────────────────────

class _AgentHierarchy extends StatelessWidget {
  final List<Map<String, dynamic>> agents;
  final Animation<double> pulseAnim;

  const _AgentHierarchy(
      {required this.agents, required this.pulseAnim});

  Map<String, dynamic>? _find(String type) {
    try {
      return agents.firstWhere((a) => a['type'] == type);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final kuine = _find('orchestrator');
    final chuwi = _find('conversational');
    final primary = ['evaluator', 'validator', 'consensus']
        .map(_find)
        .whereType<Map<String, dynamic>>()
        .toList();
    final secondary = ['predictor', 'vision', 'reporter']
        .map(_find)
        .whereType<Map<String, dynamic>>()
        .toList();
    final utility = ['price', 'stock', 'notifier']
        .map(_find)
        .whereType<Map<String, dynamic>>()
        .toList();

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          // Kuine — orchestrator
          if (kuine != null) ...[
            _HierarchyAgentCard(
                agent: kuine, pulseAnim: pulseAnim, isOrchestrator: true),
            const SizedBox(height: 4),
            _ConnectorLine(label: 'coordina'),
            const SizedBox(height: 4),
          ],

          // Chuwi — interface
          if (chuwi != null) ...[
            Row(children: [
              Expanded(
                  child: _HierarchyAgentCard(
                      agent: chuwi, pulseAnim: pulseAnim)),
            ]),
            const SizedBox(height: 4),
            _ConnectorLine(label: 'delega a'),
            const SizedBox(height: 4),
          ],

          // Primary analysis agents
          if (primary.isNotEmpty) ...[
            _AgentRow(agents: primary, pulseAnim: pulseAnim),
            const SizedBox(height: 4),
            _ConnectorLine(label: 'apoya a'),
            const SizedBox(height: 4),
          ],

          // Secondary agents
          if (secondary.isNotEmpty) ...[
            _AgentRow(agents: secondary, pulseAnim: pulseAnim),
            const SizedBox(height: 4),
            _ConnectorLine(label: '+'),
            const SizedBox(height: 4),
          ],

          // Utility agents
          if (utility.isNotEmpty)
            _AgentRow(agents: utility, pulseAnim: pulseAnim),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _ConnectorLine extends StatelessWidget {
  final String label;
  const _ConnectorLine({required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      const Expanded(child: Divider(color: Color(0xFFE5E7EB))),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Text(label,
            style: const TextStyle(fontSize: 10, color: Color(0xFFB5B5B5))),
      ),
      const Expanded(child: Divider(color: Color(0xFFE5E7EB))),
    ]);
  }
}

class _AgentRow extends StatelessWidget {
  final List<Map<String, dynamic>> agents;
  final Animation<double> pulseAnim;
  const _AgentRow({required this.agents, required this.pulseAnim});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: agents
          .asMap()
          .entries
          .map((e) => [
                if (e.key > 0) const SizedBox(width: 8),
                Expanded(
                    child: _HierarchyAgentCard(
                        agent: e.value, pulseAnim: pulseAnim)),
              ])
          .expand((w) => w)
          .toList(),
    );
  }
}

class _HierarchyAgentCard extends StatelessWidget {
  final Map<String, dynamic> agent;
  final Animation<double> pulseAnim;
  final bool isOrchestrator;

  const _HierarchyAgentCard({
    required this.agent,
    required this.pulseAnim,
    this.isOrchestrator = false,
  });

  @override
  Widget build(BuildContext context) {
    final name = agent['name'] as String? ?? '';
    final type = agent['type'] as String? ?? '';
    final model = agent['model'] as String? ?? '';
    final status = agent['status'] as String? ?? 'unknown';
    final desc = agent['description'] as String? ?? '';
    final color = _agentColor(type);
    final icon = _agentIcon(type);
    final isActive = status == 'active';

    return GestureDetector(
      onTap: () => _showDetail(context, agent),
      child: Container(
        padding: EdgeInsets.all(isOrchestrator ? 16 : 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isOrchestrator
                ? color.withValues(alpha: 0.5)
                : color.withValues(alpha: 0.15),
            width: isOrchestrator ? 2 : 1,
          ),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: isOrchestrator ? 0.2 : 0.07),
              blurRadius: isOrchestrator ? 16 : 8,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: isOrchestrator
            ? Row(children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                        colors: [color, color.withValues(alpha: 0.7)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: Icon(icon, color: Colors.white, size: 26),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Text(name,
                            style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 16,
                                color: Color(0xFF111827))),
                        const SizedBox(width: 6),
                        _ModelBadge(model),
                      ]),
                      const SizedBox(height: 2),
                      Text(desc,
                          style: const TextStyle(
                              fontSize: 11,
                              color: Color(0xFF6B7280),
                              height: 1.3),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
                AnimatedBuilder(
                  animation: pulseAnim,
                  builder: (_, __) => Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      color: isActive
                          ? const Color(0xFF059669)
                          : const Color(0xFFEF4444),
                      shape: BoxShape.circle,
                      boxShadow: isActive
                          ? [
                              BoxShadow(
                                  color: const Color(0xFF059669)
                                      .withValues(alpha: pulseAnim.value * 0.6),
                                  blurRadius: 8,
                                  spreadRadius: 2)
                            ]
                          : null,
                    ),
                  ),
                ),
              ])
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        width: 30,
                        height: 30,
                        decoration: BoxDecoration(
                          color: color.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Icon(icon, color: color, size: 16),
                      ),
                      AnimatedBuilder(
                        animation: pulseAnim,
                        builder: (_, __) => Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: isActive
                                ? const Color(0xFF059669)
                                : const Color(0xFFEF4444),
                            shape: BoxShape.circle,
                            boxShadow: isActive
                                ? [
                                    BoxShadow(
                                        color: const Color(0xFF059669)
                                            .withValues(
                                                alpha: pulseAnim.value * 0.5),
                                        blurRadius: 5,
                                        spreadRadius: 1)
                                  ]
                                : null,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 7),
                  Text(name,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                          color: Color(0xFF111827)),
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  _ModelBadge(model),
                ],
              ),
      ),
    );
  }

  void _showDetail(BuildContext context, Map<String, dynamic> a) {
    final name = a['name'] ?? '';
    final type = a['type'] ?? '';
    final model = a['model'] ?? '';
    final desc = a['description'] ?? '';
    final status = a['status'] ?? 'unknown';
    final caps = List<String>.from(a['capabilities'] ?? []);
    final lastRun = a['last_run'] as String? ?? '';
    final lastRunStr = lastRun.isNotEmpty
        ? DateTime.tryParse(lastRun)?.toLocal().toString().substring(0, 16) ??
            lastRun
        : 'Sin registros';
    final color = _agentColor(type);
    final icon = _agentIcon(type);

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.55,
        maxChildSize: 0.9,
        minChildSize: 0.4,
        expand: false,
        builder: (_, scroll) => Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: ListView(
            controller: scroll,
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(
                      color: Colors.grey.shade200,
                      borderRadius: BorderRadius.circular(2)),
                ),
              ),
              Row(children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                        colors: [color, color.withValues(alpha: 0.7)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: Colors.white, size: 28),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name,
                          style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.5)),
                      const SizedBox(height: 4),
                      Row(children: [
                        _ModelBadge(model),
                        const SizedBox(width: 6),
                        _TypeBadge(type: type, color: color),
                      ]),
                    ],
                  ),
                ),
                _StatusPill(status: status),
              ]),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: const Color(0xFFF8F9FB),
                    borderRadius: BorderRadius.circular(12)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Descripción',
                        style: TextStyle(
                            fontSize: 11,
                            color: Colors.grey.shade500,
                            fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    Text(desc,
                        style: const TextStyle(
                            fontSize: 14,
                            height: 1.55,
                            color: Color(0xFF374151))),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Row(children: [
                const Icon(Icons.schedule_rounded, size: 14, color: Colors.grey),
                const SizedBox(width: 6),
                Text('Último run: $lastRunStr',
                    style:
                        const TextStyle(fontSize: 12, color: Colors.grey)),
              ]),
              if (caps.isNotEmpty) ...[
                const SizedBox(height: 18),
                Text('Capacidades',
                    style: TextStyle(
                        fontSize: 11,
                        color: Colors.grey.shade500,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: caps
                      .map((c) => Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 5),
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                  color: color.withValues(alpha: 0.25)),
                            ),
                            child: Text(c,
                                style: TextStyle(
                                    fontSize: 12,
                                    color: color,
                                    fontWeight: FontWeight.w500)),
                          ))
                      .toList(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// ── Shared small widgets ──────────────────────────────────────────────────────

class _ModelBadge extends StatelessWidget {
  final String model;
  const _ModelBadge(this.model);

  @override
  Widget build(BuildContext context) {
    final Color c;
    final String label;
    if (model.contains('opus')) {
      c = const Color(0xFF7C3AED);
      label = 'Opus 4.7';
    } else if (model.contains('haiku')) {
      c = const Color(0xFF0891B2);
      label = 'Haiku 4.5';
    } else if (model.contains('3-5')) {
      c = const Color(0xFF0284C7);
      label = 'Sonnet 3.5';
    } else {
      c = const Color(0xFF3B82F6);
      label = 'Sonnet 4.6';
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 9, color: c, fontWeight: FontWeight.w700)),
    );
  }
}

class _TypeBadge extends StatelessWidget {
  final String type;
  final Color color;
  const _TypeBadge({required this.type, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(type.toUpperCase(),
          style: TextStyle(
              fontSize: 9, color: color, fontWeight: FontWeight.w700)),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    final isActive = status == 'active';
    final c = isActive ? const Color(0xFF059669) : const Color(0xFFEF4444);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
        const SizedBox(width: 5),
        Text(isActive ? 'ACTIVO' : 'INACTIVO',
            style: TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, color: c)),
      ]),
    );
  }
}

// ── Tab 2: Conversaciones ─────────────────────────────────────────────────────

class _ConversationsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(_agentConversationsProvider).when(
      data: (convs) => convs.isEmpty
          ? _EmptyState(
              icon: Icons.chat_bubble_outline_rounded,
              title: 'Sin conversaciones aún',
              subtitle: 'Escribe a @ChuwiMermaOpsBot en Telegram')
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              itemCount: convs.length,
              itemBuilder: (_, i) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _ConvCard(conv: convs[i]),
              ),
            ),
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorBanner(e.toString())),
    );
  }
}

class _ConvCard extends StatelessWidget {
  final Map<String, dynamic> conv;
  const _ConvCard({required this.conv});

  @override
  Widget build(BuildContext context) {
    final convId = conv['id'] as String? ?? '';
    final msgCount = conv['message_count'] ?? 0;
    final userId = conv['telegram_user_id'] ?? '?';
    final lastMsg = conv['last_message_at'] ?? '';
    final lastDate = lastMsg.isNotEmpty
        ? DateTime.tryParse(lastMsg)?.toLocal().toString().substring(0, 16)
        : null;
    final short = userId.toString().length > 5
        ? userId.toString().substring(0, 5)
        : userId.toString();

    return GestureDetector(
      onTap: convId.isNotEmpty
          ? () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => ConversationMessagesScreen(
                      conversationId: convId,
                      userId: userId.toString()),
                ),
              )
          : null,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 8,
                offset: const Offset(0, 2))
          ],
        ),
        child: Row(children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFF3B82F6), Color(0xFF60A5FA)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.chat_rounded, color: Colors.white, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Usuario Telegram $short…',
                    style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                        color: Color(0xFF111827))),
                const SizedBox(height: 2),
                Text(
                    '$msgCount mensajes${lastDate != null ? ' · $lastDate' : ''}',
                    style: const TextStyle(
                        fontSize: 11, color: Color(0xFF6B7280))),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFFEFF6FF),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text('$msgCount',
                style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFF2563EB))),
          ),
          const SizedBox(width: 6),
          const Icon(Icons.chevron_right_rounded,
              size: 18, color: Color(0xFFD1D5DB)),
        ]),
      ),
    );
  }
}

// ── Tab 3: Kuine Runs ─────────────────────────────────────────────────────────

class _RunsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(_agentRunsProvider).when(
      data: (runs) => runs.isEmpty
          ? _EmptyState(
              icon: Icons.play_circle_outline_rounded,
              title: 'Sin runs registrados',
              subtitle: 'Genera un brief para ver el trace de Kuine')
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              itemCount: runs.length,
              itemBuilder: (_, i) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _RunCard(run: runs[i]),
              ),
            ),
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorBanner(e.toString())),
    );
  }
}

class _RunCard extends StatelessWidget {
  final Map<String, dynamic> run;
  const _RunCard({required this.run});

  @override
  Widget build(BuildContext context) {
    final agentType =
        (run['agent_type'] ?? '').toString().replaceAll('kuine_', '');
    final toolsCount = run['tools_count'] ?? 0;
    final durationMs = (run['duration_ms'] as num?)?.toInt() ?? 0;
    final startedAt = run['started_at'] ?? '';
    final dateStr = startedAt.isNotEmpty
        ? DateTime.tryParse(startedAt)?.toLocal().toString().substring(0, 16)
        : null;
    final toolsList = List<dynamic>.from(run['tools_used'] ?? [])
        .where((t) => t != null && t.toString().isNotEmpty && t != 'null')
        .toList();

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 8,
              offset: const Offset(0, 2))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                    colors: [Color(0xFF7C3AED), Color(0xFFA855F7)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.psychology_rounded,
                  color: Colors.white, size: 20),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Kuine — $agentType',
                      style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: Color(0xFF111827))),
                  if (dateStr != null)
                    Text(dateStr,
                        style: const TextStyle(
                            fontSize: 11, color: Color(0xFF6B7280))),
                ],
              ),
            ),
            Row(children: [
              _Pill(
                  icon: Icons.build_rounded,
                  value: '$toolsCount',
                  color: const Color(0xFF7C3AED)),
              if (durationMs > 0) ...[
                const SizedBox(width: 6),
                _Pill(
                    icon: Icons.timer_rounded,
                    value: '${(durationMs / 1000).toStringAsFixed(1)}s',
                    color: const Color(0xFF059669)),
              ],
            ]),
          ]),
          if (toolsList.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 5,
              runSpacing: 5,
              children: toolsList.take(10).map((t) => Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3E8FF),
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(color: const Color(0xFFDDD6FE)),
                    ),
                    child: Text(t.toString(),
                        style: const TextStyle(
                            fontSize: 10, color: Color(0xFF6D28D9))),
                  )).toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final IconData icon;
  final String value;
  final Color color;
  const _Pill({required this.icon, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(7),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 11, color: color),
        const SizedBox(width: 3),
        Text(value,
            style: TextStyle(
                fontSize: 11, color: color, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

// ── Tab 4: Decisiones ─────────────────────────────────────────────────────────

class _DecisionsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(_supervisorDecisionsProvider).when(
      data: (data) {
        final decisions =
            List<Map<String, dynamic>>.from(data['decisions'] ?? []);
        final summary = Map<String, dynamic>.from(data['summary'] ?? {});
        if (decisions.isEmpty) {
          return _EmptyState(
              icon: Icons.rule_rounded,
              title: 'Sin decisiones registradas',
              subtitle: 'Kuine registra decisiones al generar el brief');
        }
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            if (summary.isNotEmpty) ...[
              _DecisionSummaryCard(summary: summary),
              const SizedBox(height: 14),
            ],
            ...decisions
                .take(20)
                .map((d) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: _DecisionCard(decision: d),
                    )),
          ],
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorBanner(e.toString())),
    );
  }
}

const _dColors = <String, Color>{
  'rebajar': Color(0xFFF59E0B),
  'donar': Color(0xFF059669),
  'retirar': Color(0xFFEF4444),
  'revisar': Color(0xFFD97706),
  'reponer': Color(0xFF3B82F6),
  'mantener': Color(0xFF6B7280),
};

const _dIcons = <String, IconData>{
  'rebajar': Icons.price_change_rounded,
  'donar': Icons.volunteer_activism_rounded,
  'retirar': Icons.delete_outline_rounded,
  'revisar': Icons.search_rounded,
  'reponer': Icons.inventory_2_rounded,
  'mantener': Icons.check_circle_outline_rounded,
};

class _DecisionSummaryCard extends StatelessWidget {
  final Map<String, dynamic> summary;
  const _DecisionSummaryCard({required this.summary});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 8,
              offset: const Offset(0, 2))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.donut_small_rounded,
                color: Color(0xFF7C3AED), size: 18),
            SizedBox(width: 8),
            Text('Resumen de decisiones de Kuine',
                style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                    color: Color(0xFF111827))),
          ]),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: summary.entries.map((e) {
              final c = _dColors[e.key] ?? const Color(0xFF6B7280);
              final ico = _dIcons[e.key] ?? Icons.help_outline_rounded;
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: c.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: c.withValues(alpha: 0.3)),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(ico, size: 14, color: c),
                  const SizedBox(width: 5),
                  Text('${e.value}',
                      style: TextStyle(
                          color: c,
                          fontWeight: FontWeight.w900,
                          fontSize: 16)),
                  const SizedBox(width: 4),
                  Text(e.key,
                      style: TextStyle(
                          color: c,
                          fontWeight: FontWeight.w600,
                          fontSize: 12)),
                ]),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  final Map<String, dynamic> decision;
  const _DecisionCard({required this.decision});

  @override
  Widget build(BuildContext context) {
    final dtype = decision['decision_type'] as String? ?? '';
    final score = decision['score'] ?? 0;
    final reason = decision['reason'] as String? ?? '';
    final validated = decision['validated'] == true;
    final createdAt = decision['created_at'] as String? ?? '';
    final dateStr = createdAt.isNotEmpty
        ? DateTime.tryParse(createdAt)?.toLocal().toString().substring(0, 16)
        : null;

    final c = _dColors[dtype] ?? const Color(0xFF6B7280);
    final ico = _dIcons[dtype] ?? Icons.help_outline_rounded;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 8,
              offset: const Offset(0, 2))
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: c.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(11),
            ),
            child: Icon(ico, color: c, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: c.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(dtype.toUpperCase(),
                        style: TextStyle(
                            color: c,
                            fontWeight: FontWeight.w800,
                            fontSize: 11)),
                  ),
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3F4F6),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text('Score $score',
                        style: const TextStyle(
                            fontSize: 11,
                            color: Color(0xFF374151),
                            fontWeight: FontWeight.w600)),
                  ),
                  const Spacer(),
                  if (validated)
                    const Icon(Icons.verified_rounded,
                        color: Color(0xFF059669), size: 16),
                  if (dateStr != null) ...[
                    const SizedBox(width: 4),
                    Text(dateStr,
                        style: const TextStyle(
                            fontSize: 10, color: Color(0xFF9CA3AF))),
                  ],
                ]),
                if (reason.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(reason,
                      style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF374151),
                          height: 1.4),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Shared ────────────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  const _EmptyState(
      {required this.icon, required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: Colors.grey.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Icon(icon, size: 36, color: Colors.grey.shade400),
          ),
          const SizedBox(height: 14),
          Text(title,
              style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 15,
                  color: Color(0xFF374151))),
          const SizedBox(height: 4),
          Text(subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: Color(0xFF9CA3AF), fontSize: 13)),
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner(this.message);

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFFECACA)),
      ),
      child: Row(children: [
        const Icon(Icons.error_outline_rounded,
            size: 16, color: Color(0xFFEF4444)),
        const SizedBox(width: 8),
        Expanded(
            child: Text(message,
                style: const TextStyle(fontSize: 12, color: Color(0xFFDC2626)))),
      ]),
    );
  }
}

// ── Conversation Messages Screen ──────────────────────────────────────────────

class ConversationMessagesScreen extends StatefulWidget {
  final String conversationId;
  final String userId;

  const ConversationMessagesScreen({
    super.key,
    required this.conversationId,
    required this.userId,
  });

  @override
  State<ConversationMessagesScreen> createState() =>
      _ConversationMessagesScreenState();
}

class _ConversationMessagesScreenState
    extends State<ConversationMessagesScreen> {
  List<Map<String, dynamic>> _messages = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMessages();
  }

  Future<void> _loadMessages() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await supabase
          .from('agent_messages')
          .select()
          .eq('conversation_id', widget.conversationId)
          .order('created_at', ascending: true);
      setState(() {
        _messages = List<Map<String, dynamic>>.from(data);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FB),
      appBar: AppBar(
        title: Text('Chuwi · Usuario ${widget.userId}'),
        centerTitle: false,
        actions: [
          IconButton(
              icon: const Icon(Icons.refresh_rounded),
              onPressed: _loadMessages),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: _ErrorBanner(_error!))
              : _messages.isEmpty
                  ? _EmptyState(
                      icon: Icons.chat_bubble_outline_rounded,
                      title: 'Sin mensajes',
                      subtitle: 'Esta conversación está vacía')
                  : ListView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                      itemCount: _messages.length,
                      itemBuilder: (_, i) =>
                          _MessageBubble(msg: _messages[i]),
                    ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final Map<String, dynamic> msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final role = msg['role'] as String? ?? 'user';
    final content = msg['content'] as String? ?? '';
    final intentTag = msg['intent_tag'] as String? ?? '';
    final agentSource = msg['agent_source'] as String? ?? '';
    final toolsUsed = List<dynamic>.from(msg['tools_used'] ?? []);
    final createdAt = msg['created_at'] as String? ?? '';
    final dateStr = createdAt.isNotEmpty
        ? DateTime.tryParse(createdAt)
                ?.toLocal()
                .toString()
                .substring(0, 16) ??
            ''
        : '';

    final isUser = role == 'user';
    final isKuine = agentSource == 'kuine';

    final Color avatarColor;
    final IconData avatarIcon;
    final String senderName;
    if (isUser) {
      avatarColor = const Color(0xFF3B82F6);
      avatarIcon = Icons.person_rounded;
      senderName = 'Encargado';
    } else if (isKuine) {
      avatarColor = const Color(0xFF7C3AED);
      avatarIcon = Icons.psychology_rounded;
      senderName = 'Kuine';
    } else {
      avatarColor = const Color(0xFF059669);
      avatarIcon = Icons.chat_rounded;
      senderName = 'Chuwi';
    }

    final bubbleBg = isUser
        ? const Color(0xFFEFF6FF)
        : isKuine
            ? const Color(0xFFF3E8FF)
            : const Color(0xFFF0FDF4);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: avatarColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(avatarIcon, size: 18, color: avatarColor),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Text(senderName,
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                          color: avatarColor)),
                  if (intentTag.isNotEmpty) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF3F4F6),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(intentTag,
                          style: const TextStyle(
                              fontSize: 9, color: Color(0xFF6B7280))),
                    ),
                  ],
                  const Spacer(),
                  Text(dateStr,
                      style: const TextStyle(
                          fontSize: 10, color: Color(0xFF9CA3AF))),
                ]),
                const SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: bubbleBg,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: avatarColor.withValues(alpha: 0.15)),
                  ),
                  child: Text(content,
                      style: const TextStyle(
                          fontSize: 13,
                          height: 1.55,
                          color: Color(0xFF374151))),
                ),
                if (toolsUsed.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: toolsUsed
                        .where((t) => t != null)
                        .map((t) => Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 7, vertical: 3),
                              decoration: BoxDecoration(
                                color: const Color(0xFFF3E8FF),
                                borderRadius: BorderRadius.circular(5),
                                border: Border.all(
                                    color: const Color(0xFFDDD6FE)),
                              ),
                              child: Text(t.toString(),
                                  style: const TextStyle(
                                      fontSize: 9,
                                      color: Color(0xFF6D28D9))),
                            ))
                        .toList(),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
