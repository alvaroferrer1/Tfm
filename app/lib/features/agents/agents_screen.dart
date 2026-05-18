import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_service.dart';

// ── Providers ────────────────────────────────────────────────────────────────

final _agentStatusProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getAgentStatus();
});

final _agentActivityProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getAgentActivity();
});

final _agentConversationsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getAgentConversations(limit: 10);
});

final _agentRunsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  return api.getAgentRuns(limit: 15);
});

final _supervisorDecisionsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getSupervisorDecisions(limit: 30);
});

// ── Screen ───────────────────────────────────────────────────────────────────

class AgentsScreen extends ConsumerStatefulWidget {
  const AgentsScreen({super.key});

  @override
  ConsumerState<AgentsScreen> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends ConsumerState<AgentsScreen>
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
      appBar: AppBar(
        title: const Text('Actividad de Agentes'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refresh,
            tooltip: 'Actualizar',
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Agentes'),
            Tab(text: 'Conversaciones'),
            Tab(text: 'Kuine Runs'),
            Tab(text: 'Decisiones'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _AgentsTab(),
          _ConversationsTab(),
          _RunsTab(),
          _DecisionsTab(),
        ],
      ),
    );
  }
}

// ── Tab: 11 Agents status ────────────────────────────────────────────────────

class _AgentsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(_agentStatusProvider);
    final activityAsync = ref.watch(_agentActivityProvider);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Activity summary
        activityAsync.when(
          data: (activity) => _ActivitySummaryCard(activity: activity),
          loading: () => const LinearProgressIndicator(),
          error: (e, _) => _ErrorChip(e.toString()),
        ),
        const SizedBox(height: 16),
        Text('11 Agentes del sistema',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        statusAsync.when(
          data: (data) {
            final agents = List<Map<String, dynamic>>.from(data['agents'] ?? []);
            return Column(
              children: agents.map((a) => _AgentCard(agent: a)).toList(),
            );
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _ErrorChip(e.toString()),
        ),
      ],
    );
  }
}

class _ActivitySummaryCard extends StatelessWidget {
  final Map<String, dynamic> activity;
  const _ActivitySummaryCard({required this.activity});

  @override
  Widget build(BuildContext context) {
    final intents = Map<String, dynamic>.from(activity['intent_breakdown'] ?? {});
    final topTools = List<dynamic>.from(activity['top_tools'] ?? []);
    final kuineCalls = activity['kuine_calls_24h'] ?? 0;
    final msgs = activity['messages_24h'] ?? 0;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.bar_chart, size: 18),
              const SizedBox(width: 6),
              Text('Ultimas 24 horas',
                  style: Theme.of(context).textTheme.titleSmall),
            ]),
            const Divider(height: 16),
            Row(children: [
              _Stat(label: 'Mensajes', value: '$msgs'),
              const SizedBox(width: 24),
              _Stat(label: 'Llamadas Kuine', value: '$kuineCalls'),
            ]),
            if (topTools.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Top tools:',
                  style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 4),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: topTools.take(6).map((t) {
                  final name = t is Map ? t['tool'] ?? t.toString() : t.toString();
                  final count = t is Map ? t['count'] ?? '' : '';
                  return Chip(
                    label: Text('$name${count != '' ? ' ($count)' : ''}',
                        style: const TextStyle(fontSize: 11)),
                    padding: EdgeInsets.zero,
                    visualDensity: VisualDensity.compact,
                  );
                }).toList(),
              ),
            ],
            if (intents.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Intenciones:',
                  style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 4),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: intents.entries.map((e) => Chip(
                  label: Text('${e.key}: ${e.value}',
                      style: const TextStyle(fontSize: 11)),
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                )).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AgentCard extends StatelessWidget {
  final Map<String, dynamic> agent;
  const _AgentCard({required this.agent});

  Color _typeColor(String type) {
    switch (type) {
      case 'orchestrator': return Colors.purple;
      case 'conversational': return Colors.blue;
      case 'evaluator': return Colors.orange;
      case 'validator': return Colors.red;
      case 'consensus': return Colors.teal;
      case 'predictor': return Colors.indigo;
      case 'vision': return Colors.pink;
      default: return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = agent['name'] ?? '';
    final type = agent['type'] ?? '';
    final model = agent['model'] ?? '';
    final desc = agent['description'] ?? '';
    final status = agent['status'] ?? 'unknown';
    final color = _typeColor(type);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Icon(Icons.smart_toy, color: color, size: 20),
        ),
        title: Row(children: [
          Text(name, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(type, style: TextStyle(fontSize: 10, color: color)),
          ),
        ]),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(model, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            Text(desc, style: const TextStyle(fontSize: 12)),
          ],
        ),
        trailing: Icon(
          status == 'active' ? Icons.check_circle : Icons.error,
          color: status == 'active' ? Colors.green : Colors.red,
          size: 18,
        ),
        isThreeLine: true,
      ),
    );
  }
}

// ── Tab: Conversaciones Chuwi ────────────────────────────────────────────────

class _ConversationsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final convAsync = ref.watch(_agentConversationsProvider);
    return convAsync.when(
      data: (convs) {
        if (convs.isEmpty) {
          return const Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.chat_bubble_outline, size: 48, color: Colors.grey),
              SizedBox(height: 8),
              Text('Sin conversaciones aun', style: TextStyle(color: Colors.grey)),
              SizedBox(height: 4),
              Text('Escribe a @ChuwiMermaOpsBot en Telegram',
                  style: TextStyle(color: Colors.grey, fontSize: 12)),
            ]),
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: convs.length,
          itemBuilder: (_, i) => _ConvCard(conv: convs[i]),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorChip(e.toString())),
    );
  }
}

class _ConvCard extends StatelessWidget {
  final Map<String, dynamic> conv;
  const _ConvCard({required this.conv});

  @override
  Widget build(BuildContext context) {
    final msgCount = conv['message_count'] ?? 0;
    final userId = conv['telegram_user_id'] ?? '?';
    final lastMsg = conv['last_message_at'] ?? '';
    final lastDate = lastMsg.isNotEmpty
        ? DateTime.tryParse(lastMsg)?.toLocal().toString().substring(0, 16)
        : '';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.chat, size: 18)),
        title: Text('Usuario $userId',
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        subtitle: Text('$msgCount mensajes${lastDate != null ? ' • $lastDate' : ''}',
            style: const TextStyle(fontSize: 12)),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.blue.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text('$msgCount msgs', style: const TextStyle(fontSize: 11)),
        ),
      ),
    );
  }
}

// ── Tab: Kuine Runs ──────────────────────────────────────────────────────────

class _RunsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final runsAsync = ref.watch(_agentRunsProvider);
    return runsAsync.when(
      data: (runs) {
        if (runs.isEmpty) {
          return const Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.play_circle_outline, size: 48, color: Colors.grey),
              SizedBox(height: 8),
              Text('Sin runs registrados', style: TextStyle(color: Colors.grey)),
              SizedBox(height: 4),
              Text('Genera un brief para ver el trace de Kuine',
                  style: TextStyle(color: Colors.grey, fontSize: 12)),
            ]),
          );
        }
        return ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: runs.length,
          itemBuilder: (_, i) => _RunCard(run: runs[i]),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorChip(e.toString())),
    );
  }
}

class _RunCard extends StatelessWidget {
  final Map<String, dynamic> run;
  const _RunCard({required this.run});

  @override
  Widget build(BuildContext context) {
    final agentType = (run['agent_type'] ?? '').toString().replaceAll('kuine_', '');
    final toolsCount = run['tools_count'] ?? 0;
    final durationMs = run['duration_ms'] ?? 0;
    final startedAt = run['started_at'] ?? '';
    final dateStr = startedAt.isNotEmpty
        ? DateTime.tryParse(startedAt)?.toLocal().toString().substring(0, 16)
        : '';
    final toolsList = List<dynamic>.from(run['tools_used'] ?? []);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.psychology, size: 16, color: Colors.purple),
              const SizedBox(width: 6),
              Text('Kuine — $agentType',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
              const Spacer(),
              if (dateStr != null)
                Text(dateStr, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ]),
            const SizedBox(height: 6),
            Row(children: [
              _Stat(label: 'Tools', value: '$toolsCount'),
              const SizedBox(width: 16),
              if (durationMs > 0)
                _Stat(label: 'Duracion', value: '${(durationMs / 1000).toStringAsFixed(1)}s'),
            ]),
            if (toolsList.isNotEmpty) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 4,
                runSpacing: 4,
                children: toolsList.take(8).map((t) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.purple.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(t.toString(), style: const TextStyle(fontSize: 10)),
                )).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Tab: Decisiones Kuine ────────────────────────────────────────────────────

class _DecisionsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final decAsync = ref.watch(_supervisorDecisionsProvider);
    return decAsync.when(
      data: (data) {
        final decisions = List<Map<String, dynamic>>.from(data['decisions'] ?? []);
        final summary = Map<String, dynamic>.from(data['summary'] ?? {});
        if (decisions.isEmpty) {
          return const Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.rule, size: 48, color: Colors.grey),
              SizedBox(height: 8),
              Text('Sin decisiones registradas', style: TextStyle(color: Colors.grey)),
              SizedBox(height: 4),
              Text('Kuine registra decisiones al generar el brief',
                  style: TextStyle(color: Colors.grey, fontSize: 12)),
            ]),
          );
        }
        return ListView(
          padding: const EdgeInsets.all(12),
          children: [
            if (summary.isNotEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Resumen de decisiones',
                          style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        children: summary.entries.map((e) => _DecisionBadge(
                          type: e.key,
                          count: e.value as int,
                        )).toList(),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 8),
            ...decisions.take(20).map((d) => _DecisionCard(decision: d)),
          ],
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: _ErrorChip(e.toString())),
    );
  }
}

class _DecisionBadge extends StatelessWidget {
  final String type;
  final int count;
  const _DecisionBadge({required this.type, required this.count});

  Color _color() {
    switch (type) {
      case 'rebajar': return Colors.orange;
      case 'donar': return Colors.green;
      case 'retirar': return Colors.red;
      case 'revisar': return Colors.amber;
      case 'reponer': return Colors.blue;
      case 'mantener': return Colors.grey;
      default: return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _color();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: c.withValues(alpha: 0.4)),
      ),
      child: Text('$type: $count',
          style: TextStyle(color: c, fontWeight: FontWeight.bold, fontSize: 12)),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  final Map<String, dynamic> decision;
  const _DecisionCard({required this.decision});

  @override
  Widget build(BuildContext context) {
    final dtype = decision['decision_type'] ?? '';
    final score = decision['score'] ?? 0;
    final reason = decision['reason'] ?? '';
    final validated = decision['validated'] == true;
    final createdAt = decision['created_at'] ?? '';
    final dateStr = createdAt.isNotEmpty
        ? DateTime.tryParse(createdAt)?.toLocal().toString().substring(0, 16)
        : '';

    Color dtypeColor() {
      switch (dtype) {
        case 'rebajar': return Colors.orange;
        case 'donar': return Colors.green;
        case 'retirar': return Colors.red;
        case 'revisar': return Colors.amber;
        case 'reponer': return Colors.blue;
        default: return Colors.grey;
      }
    }

    final c = dtypeColor();

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: c.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(dtype.toUpperCase(),
                    style: TextStyle(color: c, fontWeight: FontWeight.bold, fontSize: 11)),
              ),
              const SizedBox(width: 8),
              Text('Score: $score', style: const TextStyle(fontSize: 12)),
              const Spacer(),
              if (validated)
                const Icon(Icons.verified, color: Colors.green, size: 16),
              if (dateStr != null)
                Text(dateStr, style: const TextStyle(fontSize: 10, color: Colors.grey)),
            ]),
            if (reason.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(reason, style: const TextStyle(fontSize: 12), maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Shared widgets ───────────────────────────────────────────────────────────

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  const _Stat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 10, color: Colors.grey)),
        Text(value,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
      ],
    );
  }
}

class _ErrorChip extends StatelessWidget {
  final String message;
  const _ErrorChip(this.message);

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: const Icon(Icons.error_outline, size: 16, color: Colors.red),
      label: Text(message, style: const TextStyle(fontSize: 11)),
    );
  }
}
