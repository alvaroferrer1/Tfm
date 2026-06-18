import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show HapticFeedback;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../core/api_service.dart';

// ── Message model ─────────────────────────────────────────────────────────────

class _Message {
  final String text;
  final bool isUser;
  final List<String> toolsUsed;
  final DateTime at;
  final bool isStreaming; // true mientras llegan tokens

  const _Message({
    required this.text,
    required this.isUser,
    this.toolsUsed = const [],
    required this.at,
    this.isStreaming = false,
  });

  _Message copyWith({String? text, bool? isStreaming, List<String>? toolsUsed}) => _Message(
    text: text ?? this.text,
    isUser: isUser,
    toolsUsed: toolsUsed ?? this.toolsUsed,
    at: at,
    isStreaming: isStreaming ?? this.isStreaming,
  );
}

// ── State ─────────────────────────────────────────────────────────────────────

class _ChatNotifier extends StateNotifier<List<_Message>> {
  _ChatNotifier() : super([]);

  void addUser(String text) {
    state = [...state, _Message(text: text, isUser: true, at: DateTime.now())];
  }

  void addKuine(String text, List<String> tools) {
    state = [...state, _Message(text: text, isUser: false, toolsUsed: tools, at: DateTime.now())];
  }

  // Streaming: añade un placeholder vacío y lo va completando token a token
  void startStreaming() {
    state = [...state, _Message(text: '', isUser: false, at: DateTime.now(), isStreaming: true)];
  }

  void appendToken(String token) {
    if (state.isEmpty) return;
    final last = state.last;
    if (!last.isStreaming) return;
    state = [...state.sublist(0, state.length - 1), last.copyWith(text: last.text + token)];
  }

  void finalizeStream(List<String> tools) {
    if (state.isEmpty) return;
    final last = state.last;
    state = [...state.sublist(0, state.length - 1), last.copyWith(isStreaming: false, toolsUsed: tools)];
  }
}

final _chatProvider = StateNotifierProvider.autoDispose<_ChatNotifier, List<_Message>>(
  (ref) => _ChatNotifier(),
);

final _loadingProvider = StateProvider.autoDispose<bool>((ref) => false);
// Muestra qué tool está usando Chuwi ahora mismo durante streaming
final _activeToolProvider = StateProvider.autoDispose<String>((ref) => '');

// ── Quick suggestions ─────────────────────────────────────────────────────────

const _suggestions = [
  '¿Qué productos caducan hoy?',
  'Dame el resumen del día',
  '¿Cuánto valor en riesgo hay ahora?',
  'Productos más urgentes con precio rebajado',
  'Ruta optimizada para hoy',
  'Estado de donaciones este mes',
  'Acciones pendientes en tienda',
];

// ── Tool label map ────────────────────────────────────────────────────────────

const _toolLabels = <String, String>{
  'get_store_overview': '📊 Consulta estado tienda',
  'get_pending_actions': '✅ Carga acciones pendientes',
  'get_daily_route': '🗺 Genera ruta del día',
  'complete_action': '✓ Registra acción',
  'analyze_product': '🔍 Analiza producto (Kuine)',
  'get_merma_stats': '📉 Estadísticas de merma',
  'get_donation_impact': '🤝 Impacto donaciones',
  'register_donation': '🏛 Registra donación',
  'get_weekly_report': '📋 Informe semanal',
  'get_agent_status_brief': '🤖 Estado de agentes',
  'get_store_comparison': '🏪 Comparativa tiendas',
  'get_esg_metrics': '🌱 Métricas ESG',
  'get_order_suggestions': '📦 Sugerencias de pedido',
  'get_risk_predictions': '🔮 Predicción de riesgo',
  'recall_store_memory': '🧠 Memoria episódica',
};

// ── Screen ────────────────────────────────────────────────────────────────────

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;

    HapticFeedback.selectionClick();
    _controller.clear();

    // Historial antes del mensaje del usuario
    final messages = ref.read(_chatProvider);
    final history = messages.map((m) => {
      'role': m.isUser ? 'user' : 'assistant',
      'content': m.text,
    }).toList();

    ref.read(_chatProvider.notifier).addUser(trimmed);
    ref.read(_loadingProvider.notifier).state = true;
    ref.read(_activeToolProvider.notifier).state = '';
    _scrollToBottom();

    bool firstToken = true;
    bool hadError = false;
    final List<String> toolsUsed = [];

    try {
      // Streaming real — primer token en <400ms
      ref.read(_chatProvider.notifier).startStreaming();

      await for (final event in api.chatWithKuineStream(
        message: trimmed,
        history: history,
      )) {
        switch (event.type) {
          case ChatStreamEventType.tool:
            // Chuwi está consultando una herramienta — mostrar en indicator
            ref.read(_activeToolProvider.notifier).state = event.toolLabel;
            toolsUsed.add(event.toolName);

          case ChatStreamEventType.token:
            if (firstToken) {
              // Primer token: haptic + quitar typing indicator
              HapticFeedback.lightImpact();
              ref.read(_loadingProvider.notifier).state = false;
              ref.read(_activeToolProvider.notifier).state = '';
              firstToken = false;
            }
            ref.read(_chatProvider.notifier).appendToken(event.content);
            _scrollToBottom();

          case ChatStreamEventType.done:
            toolsUsed.addAll(event.tools.where((t) => !toolsUsed.contains(t)));
            ref.read(_chatProvider.notifier).finalizeStream(toolsUsed);
            // Haptic final según complejidad
            if (toolsUsed.any((t) => t.contains('analyze') || t.contains('kuine'))) {
              HapticFeedback.mediumImpact();
            } else {
              HapticFeedback.lightImpact();
            }

          case ChatStreamEventType.error:
            hadError = true;
            ref.read(_chatProvider.notifier).finalizeStream([]);
            HapticFeedback.heavyImpact();
        }
      }

      if (hadError && firstToken) {
        // No hubo tokens — reemplazar placeholder con mensaje de error
        ref.read(_chatProvider.notifier).finalizeStream([]);
        ref.read(_chatProvider.notifier).addKuine(
          'No he podido procesar tu mensaje. Comprueba la conexión e inténtalo de nuevo.',
          [],
        );
      }
    } catch (e) {
      HapticFeedback.heavyImpact();
      ref.read(_chatProvider.notifier).finalizeStream([]);
      final msg = e.toString().toLowerCase();
      final isTimeout = msg.contains('timeout');
      final isNoInternet = msg.contains('connection refused') ||
          msg.contains('network') ||
          msg.contains('socket') ||
          msg.contains('errno = 111') ||
          msg.contains('failed host lookup');
      ref.read(_chatProvider.notifier).addKuine(
        isTimeout
            ? 'Tardé demasiado en responder. Inténtalo con una pregunta más concreta.'
            : isNoInternet
                ? 'Necesito conexión a internet real para funcionar — no basta con Wi-Fi local sin salida a internet. Cuando tengas conexión, podré responderte con normalidad.'
                : 'No he podido responder ahora mismo. Comprueba la conexión e inténtalo de nuevo.',
        [],
      );
    } finally {
      ref.read(_loadingProvider.notifier).state = false;
      ref.read(_activeToolProvider.notifier).state = '';
      _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final messages = ref.watch(_chatProvider);
    final loading = ref.watch(_loadingProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: const Color(0xFF7C3AED),
        foregroundColor: Colors.white,
        title: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Text('Chuwi', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                Text('Coordinado por Kuine · 12 agentes activos', style: TextStyle(fontSize: 10, color: Colors.white70)),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Nueva conversación',
            onPressed: () {
              ref.invalidate(_chatProvider);
              ref.invalidate(_loadingProvider);
            },
          ),
        ],
        elevation: 0,
      ),
      body: Column(
        children: [
          if (messages.isNotEmpty) _SuggestionsBar(onTap: _send),

          // Active tool banner
          Consumer(builder: (_, ref, __) {
            final activeTool = ref.watch(_activeToolProvider);
            if (activeTool.isEmpty) return const SizedBox.shrink();
            return AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              color: const Color(0xFF7C3AED).withValues(alpha: 0.08),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Row(children: [
                const SizedBox(
                  width: 12, height: 12,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF7C3AED)),
                ),
                const SizedBox(width: 8),
                Text(activeTool, style: const TextStyle(fontSize: 11, color: Color(0xFF7C3AED), fontWeight: FontWeight.w500)),
              ]),
            );
          }),

          // Messages
          Expanded(
            child: messages.isEmpty && !loading
                ? _WelcomeView(onSuggestion: _send)
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    itemCount: messages.length + (loading ? 1 : 0),
                    itemBuilder: (ctx2, i) {
                      if (i == messages.length) return const _TypingIndicator();
                      return _MessageBubble(msg: messages[i]);
                    },
                  ),
          ),

          // Input
          _InputBar(controller: _controller, onSend: _send, loading: loading),
        ],
      ),
    );
  }
}

// ── Welcome view ──────────────────────────────────────────────────────────────

class _WelcomeView extends StatelessWidget {
  final void Function(String) onSuggestion;
  const _WelcomeView({required this.onSuggestion});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
      children: [
        // Avatar + nombre
        Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF7C3AED), Color(0xFF5B21B6)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(18),
              ),
              child: const Icon(Icons.psychology_rounded, size: 28, color: Colors.white),
            ),
            const SizedBox(width: 14),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Hola, soy Chuwi',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Color(0xFF111827))),
                  SizedBox(height: 3),
                  Text('Coordinado por Kuine · 12 agentes activos',
                      style: TextStyle(fontSize: 12, color: Color(0xFF7C3AED), fontWeight: FontWeight.w500)),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        // Descripción
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFF5F3FF),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFDDD6FE)),
          ),
          child: const Text(
            'Tengo acceso en tiempo real a los datos de tu tienda: productos, caducidades, acciones pendientes, estadísticas de merma y donaciones. Puedo analizar fotos de productos, generar rutas optimizadas y coordinar a Kuine para decisiones complejas.',
            style: TextStyle(fontSize: 13, color: Color(0xFF374151), height: 1.55),
          ),
        ),
        const SizedBox(height: 16),
        // Capacidades
        const Text('¿Qué puedo hacer?',
            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        const SizedBox(height: 10),
        ...[
          ('📦', 'Consultar stock y caducidades', 'Sé cuántas unidades quedan y cuándo caducan'),
          ('🗺', 'Generar ruta del día', 'Optimizo el recorrido por pasillos según urgencia'),
          ('📊', 'Resumen de merma y ESG', 'Cuánto valor recuperado, CO₂ evitado, donaciones'),
          ('🤖', 'Analizar con Kuine', 'Para decisiones complejas activo al orquestador'),
          ('📷', 'Analizar fotos de productos', 'Envía una imagen para análisis visual de estado'),
        ].map((item) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(item.$1, style: const TextStyle(fontSize: 16)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.$2,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF111827))),
                    Text(item.$3,
                        style: const TextStyle(fontSize: 11, color: Color(0xFF6B7280))),
                  ],
                ),
              ),
            ],
          ),
        )),
        const SizedBox(height: 16),
        const Text('Prueba a preguntar:',
            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF111827))),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _suggestions.take(4).map((s) => GestureDetector(
            onTap: () => onSuggestion(s),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFFEDE9FE),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFDDD6FE)),
              ),
              child: Text(s,
                  style: const TextStyle(fontSize: 12, color: Color(0xFF5B21B6), fontWeight: FontWeight.w500)),
            ),
          )).toList(),
        ),
      ],
    );
  }
}

// ── Suggestions bar ───────────────────────────────────────────────────────────

class _SuggestionsBar extends StatelessWidget {
  final void Function(String) onTap;
  const _SuggestionsBar({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: _suggestions.map((s) => Padding(
            padding: const EdgeInsets.only(right: 8),
            child: GestureDetector(
              onTap: () => onTap(s),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: BoxDecoration(
                  color: const Color(0xFFEDE9FE),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFDDD6FE)),
                ),
                child: Text(s,
                    style: const TextStyle(
                        fontSize: 12,
                        color: Color(0xFF5B21B6),
                        fontWeight: FontWeight.w500)),
              ),
            ),
          )).toList(),
        ),
      ),
    );
  }
}

// ── Streaming text — muestra texto con cursor parpadeante mientras llegan tokens ──

class _StreamingText extends StatefulWidget {
  final String text;
  const _StreamingText({required this.text});

  @override
  State<_StreamingText> createState() => _StreamingTextState();
}

class _StreamingTextState extends State<_StreamingText>
    with SingleTickerProviderStateMixin {
  late AnimationController _cursorCtrl;
  late Animation<double> _cursorAnim;

  @override
  void initState() {
    super.initState();
    _cursorCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    )..repeat(reverse: true);
    _cursorAnim = Tween<double>(begin: 0, end: 1)
        .animate(CurvedAnimation(parent: _cursorCtrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _cursorCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _cursorAnim,
      builder: (_, __) => Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: widget.text,
              style: const TextStyle(
                fontSize: 14, color: Color(0xFF1F2937), height: 1.45,
              ),
            ),
            // Cursor parpadeante al final del stream
            TextSpan(
              text: '▋',
              style: TextStyle(
                fontSize: 14,
                color: const Color(0xFF7C3AED).withValues(alpha: _cursorAnim.value),
                height: 1.45,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Message bubble ────────────────────────────────────────────────────────────

class _MessageBubble extends StatelessWidget {
  final _Message msg;
  const _MessageBubble({required this.msg});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.isUser;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            Container(
              width: 28,
              height: 28,
              margin: const EdgeInsets.only(right: 6, bottom: 2),
              decoration: BoxDecoration(
                color: const Color(0xFF7C3AED),
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 14),
            ),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: isUser ? const Color(0xFF7C3AED) : Colors.white,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(16),
                      topRight: const Radius.circular(16),
                      bottomLeft: Radius.circular(isUser ? 16 : 4),
                      bottomRight: Radius.circular(isUser ? 4 : 16),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.06),
                        blurRadius: 4,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: msg.isStreaming
                      ? _StreamingText(text: msg.text)
                      : SelectableText(
                          msg.text,
                          style: TextStyle(
                            fontSize: 14,
                            color: isUser ? Colors.white : const Color(0xFF1F2937),
                            height: 1.45,
                          ),
                        ),
                ),
                if (msg.toolsUsed.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: msg.toolsUsed.take(4).map((t) {
                      final label = _toolLabels[t] ?? t;
                      return Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFFEDE9FE),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(label, style: const TextStyle(fontSize: 10, color: Color(0xFF7C3AED))),
                      );
                    }).toList(),
                  ),
                ],
              ],
            ),
          ),
          if (isUser) const SizedBox(width: 6),
        ],
      ),
    );
  }
}

// ── Typing indicator — tres fases semánticas ─────────────────────────────────
// Fase 1 (0-1s):   "Procesando intención..."  — icono brain
// Fase 2 (1-3s):   "Consultando datos..."      — icono storage
// Fase 3 (3s+):    "Coordinando con Kuine..."  — icono hub
// Hace que la espera se sienta como trabajo real, no spinner genérico.

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with TickerProviderStateMixin {
  late AnimationController _dotCtrl;
  late AnimationController _pulseCtrl;
  late Animation<double> _dotAnim;
  late Animation<double> _pulseAnim;

  int _phase = 0;

  static const _phases = [
    (Icons.psychology_outlined,    'Procesando intención...',    Color(0xFF7C3AED)),
    (Icons.storage_rounded,        'Consultando datos...',       Color(0xFF0891B2)),
    (Icons.hub_rounded,            'Coordinando con Kuine...',   Color(0xFF059669)),
  ];

  @override
  void initState() {
    super.initState();
    _dotCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat(reverse: true);
    _dotAnim = Tween<double>(begin: 0.2, end: 1.0)
        .animate(CurvedAnimation(parent: _dotCtrl, curve: Curves.easeInOut));
    _pulseAnim = Tween<double>(begin: 0.6, end: 1.0)
        .animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    Future.delayed(const Duration(milliseconds: 1000), () {
      if (mounted) setState(() => _phase = 1);
    });
    Future.delayed(const Duration(milliseconds: 3000), () {
      if (mounted) setState(() => _phase = 2);
    });
  }

  @override
  void dispose() {
    _dotCtrl.dispose();
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final (icon, label, color) = _phases[_phase];

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // Avatar pulsante
          AnimatedBuilder(
            animation: _pulseAnim,
            builder: (_, __) => Transform.scale(
              scale: _pulseAnim.value,
              child: Container(
                width: 30, height: 30,
                margin: const EdgeInsets.only(right: 8, bottom: 2),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(10),
                  boxShadow: [
                    BoxShadow(color: color.withValues(alpha: _pulseAnim.value * 0.4), blurRadius: 8)
                  ],
                ),
                child: Icon(icon, color: Colors.white, size: 16),
              ),
            ),
          ),

          // Burbuja de estado
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            child: Container(
              key: ValueKey(_phase),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16).copyWith(bottomLeft: const Radius.circular(4)),
                boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 4, offset: const Offset(0, 2))],
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(label, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w500)),
                const SizedBox(width: 6),
                // Tres puntos animados
                AnimatedBuilder(
                  animation: _dotAnim,
                  builder: (_, __) => Row(
                    mainAxisSize: MainAxisSize.min,
                    children: List.generate(3, (i) => Opacity(
                      opacity: ((_dotAnim.value + i * 0.3) % 1.0).clamp(0.2, 1.0),
                      child: Padding(
                        padding: const EdgeInsets.only(right: 2),
                        child: Container(
                          width: 4, height: 4,
                          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                        ),
                      ),
                    )),
                  ),
                ),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Input bar ─────────────────────────────────────────────────────────────────

class _InputBar extends StatefulWidget {
  final TextEditingController controller;
  final void Function(String) onSend;
  final bool loading;

  const _InputBar({required this.controller, required this.onSend, required this.loading});

  @override
  State<_InputBar> createState() => _InputBarState();
}

class _InputBarState extends State<_InputBar> {
  final _stt = SpeechToText();
  bool _sttAvailable = false;
  bool _listening = false;

  @override
  void initState() {
    super.initState();
    _initStt();
  }

  Future<void> _initStt() async {
    try {
      final ok = await _stt.initialize(onError: (_) => _stopListening());
      if (mounted) setState(() => _sttAvailable = ok);
    } catch (_) {
      if (mounted) setState(() => _sttAvailable = false);
    }
  }

  Future<void> _toggleMic() async {
    if (_listening) {
      _stopListening();
      return;
    }
    if (!_sttAvailable) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('El micrófono no está disponible en este dispositivo.'),
          duration: Duration(seconds: 3),
        ),
      );
      return;
    }
    setState(() => _listening = true);
    await _stt.listen(
      onResult: (r) {
        if (r.finalResult) {
          widget.controller.text = r.recognizedWords;
          widget.controller.selection = TextSelection.fromPosition(
            TextPosition(offset: widget.controller.text.length),
          );
          _stopListening();
        }
      },
      listenOptions: SpeechListenOptions(
        localeId: 'es_ES',
        listenFor: const Duration(seconds: 30),
        pauseFor: const Duration(seconds: 4),
      ),
    );
  }

  void _stopListening() {
    _stt.stop();
    if (mounted) setState(() => _listening = false);
  }

  @override
  void dispose() {
    _stt.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 12,
        right: 8,
        top: 8,
        bottom: MediaQuery.of(context).padding.bottom + 8,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 8, offset: const Offset(0, -2))],
      ),
      child: Row(
        children: [
          // Mic button
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            child: IconButton(
              icon: Icon(
                _listening ? Icons.stop_circle_rounded : Icons.mic_rounded,
                color: _listening ? Colors.red : const Color(0xFF9CA3AF),
              ),
              tooltip: _listening ? 'Detener grabación' : 'Dictar mensaje',
              onPressed: widget.loading ? null : _toggleMic,
            ),
          ),
          // Text field
          Expanded(
            child: TextField(
              controller: widget.controller,
              maxLines: null,
              textInputAction: TextInputAction.newline,
              decoration: InputDecoration(
                hintText: _listening ? 'Escuchando…' : 'Escribe a Chuwi…',
                hintStyle: TextStyle(
                  color: _listening ? const Color(0xFF7C3AED) : const Color(0xFF9CA3AF),
                ),
                filled: true,
                fillColor: _listening
                    ? const Color(0xFFF5F3FF)
                    : const Color(0xFFF9FAFB),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide(color: Colors.grey.shade200),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide(
                    color: _listening
                        ? const Color(0xFF7C3AED)
                        : Colors.grey.shade200,
                    width: _listening ? 1.5 : 1,
                  ),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: const BorderSide(color: Color(0xFF7C3AED), width: 1.5),
                ),
              ),
              onSubmitted: widget.loading ? null : widget.onSend,
            ),
          ),
          const SizedBox(width: 8),
          // Send button
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            child: widget.loading
                ? const SizedBox(
                    width: 44,
                    height: 44,
                    child: Padding(
                      padding: EdgeInsets.all(10),
                      child: CircularProgressIndicator(strokeWidth: 2.5, color: Color(0xFF7C3AED)),
                    ),
                  )
                : IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: const Color(0xFF7C3AED),
                      foregroundColor: Colors.white,
                    ),
                    icon: const Icon(Icons.send_rounded),
                    onPressed: () => widget.onSend(widget.controller.text),
                  ),
          ),
        ],
      ),
    );
  }
}
