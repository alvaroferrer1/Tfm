import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  final _storeCodeCtrl = TextEditingController();
  int _page = 0;

  static const _pages = [
    _PageData(
      emoji: '🧠',
      title: 'MermaOps',
      subtitle: 'El problema que resuelve',
      body:
          'El desperdicio alimentario cuesta a un supermercado entre el 2% y el 5% de sus ingresos cada año.\n\n'
          'MermaOps usa inteligencia artificial para detectar qué productos están en riesgo, '
          'decidir qué hacer con ellos y guiar al personal — en tiempo real, sin hardware adicional.',
      color: Color(0xFF059669),
      bgColor: Color(0xFFF0FDF4),
    ),
    _PageData(
      emoji: '⚡',
      title: 'Kuine',
      subtitle: 'El orquestador inteligente',
      body:
          'Kuine analiza toda la tienda cada mañana a las 7:30 con 16 herramientas de IA.\n\n'
          'Evalúa cada lote, calcula descuentos exactos, propone donaciones al banco de alimentos '
          'y genera el brief diario con trazabilidad completa.\n\n'
          'Funciona solo. Sin que nadie se lo pida.',
      color: Color(0xFF7C3AED),
      bgColor: Color(0xFFF5F3FF),
    ),
    _PageData(
      emoji: '💬',
      title: 'Chuwi',
      subtitle: 'Tu agente en Telegram',
      body:
          'Chuwi no es un bot de comandos. Es un agente real que razona con datos de la tienda '
          'y responde en lenguaje natural.\n\n'
          'Escríbele desde Telegram: "¿qué hay crítico hoy?", envíale una foto de un producto '
          'o una nota de voz — y él actúa.\n\n'
          'También te avisa solo cuando algo cambia.',
      color: Color(0xFF2AABEE),
      bgColor: Color(0xFFF0F9FF),
    ),
    _PageData(
      emoji: '🏪',
      title: 'Tu tienda',
      subtitle: 'Conecta en segundos',
      body:
          'Introduce el código de tienda que te facilita tu responsable.\n\n'
          'Si no lo tienes ahora, puedes dejarlo vacío y configurarlo desde el perfil más tarde.',
      color: Color(0xFFD97706),
      bgColor: Color(0xFFEFF6FF),
      isStorePage: true,
    ),
  ];

  void _finish() {
    final code = _storeCodeCtrl.text.trim();
    SharedPreferences.getInstance().then((prefs) {
      prefs.setBool('onboarding_done', true);
      if (code.isNotEmpty) prefs.setString('user_store_id', code);
    });
    if (mounted) context.go('/login');
  }

  void _nextPage() {
    if (_page < _pages.length - 1) {
      _controller.nextPage(duration: const Duration(milliseconds: 350), curve: Curves.easeInOut);
    } else {
      _finish();
    }
  }

  void _prevPage() {
    if (_page > 0) {
      _controller.previousPage(duration: const Duration(milliseconds: 350), curve: Curves.easeInOut);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _storeCodeCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isWide = MediaQuery.of(context).size.width >= 720;
    final cur = _pages[_page];

    return Scaffold(
      backgroundColor: cur.bgColor,
      body: SafeArea(
        child: Column(
          children: [
            // Top bar: back + dots + skip
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  AnimatedOpacity(
                    opacity: _page > 0 ? 1.0 : 0.0,
                    duration: const Duration(milliseconds: 200),
                    child: IconButton(
                      icon: Icon(Icons.arrow_back_ios_new_rounded,
                          color: cur.color.withValues(alpha: 0.7), size: 18),
                      onPressed: _page > 0 ? _prevPage : null,
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: List.generate(_pages.length, (i) {
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 250),
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: i == _page ? 20 : 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color: i == _page
                              ? cur.color
                              : cur.color.withValues(alpha: 0.25),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      );
                    }),
                  ),
                  TextButton(
                    onPressed: _finish,
                    child: Text('Saltar',
                        style: TextStyle(
                            color: cur.color.withValues(alpha: 0.7), fontSize: 14)),
                  ),
                ],
              ),
            ),

            // Page content
            Expanded(
              child: PageView.builder(
                controller: _controller,
                onPageChanged: (i) => setState(() => _page = i),
                itemCount: _pages.length,
                itemBuilder: (context, i) => _OnboardingPage(
                  data: _pages[i],
                  storeCodeCtrl: _pages[i].isStorePage ? _storeCodeCtrl : null,
                  isWide: isWide,
                ),
              ),
            ),

            // Bottom button
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 0, 32, 40),
              child: isWide
                  ? Row(children: [
                      AnimatedOpacity(
                        opacity: _page > 0 ? 1.0 : 0.0,
                        duration: const Duration(milliseconds: 200),
                        child: IconButton(
                          icon: Icon(Icons.arrow_back_ios_rounded, color: cur.color),
                          onPressed: _page > 0 ? _prevPage : null,
                        ),
                      ),
                      const Spacer(),
                      SizedBox(
                        width: 200,
                        height: 50,
                        child: _ActionButton(
                            page: cur,
                            onPressed: _nextPage,
                            isLast: _page == _pages.length - 1),
                      ),
                      const Spacer(),
                      const SizedBox(width: 48),
                    ])
                  : SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: _ActionButton(
                          page: cur,
                          onPressed: _nextPage,
                          isLast: _page == _pages.length - 1),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final _PageData page;
  final VoidCallback onPressed;
  final bool isLast;
  const _ActionButton(
      {required this.page, required this.onPressed, required this.isLast});

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      style: ElevatedButton.styleFrom(
        backgroundColor: page.color,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        elevation: 0,
      ),
      onPressed: onPressed,
      child: Text(
        isLast ? 'Empezar' : 'Siguiente',
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _OnboardingPage extends StatelessWidget {
  final _PageData data;
  final TextEditingController? storeCodeCtrl;
  final bool isWide;

  const _OnboardingPage(
      {required this.data, this.storeCodeCtrl, required this.isWide});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: isWide ? 540 : double.infinity),
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SizedBox(height: 16),
              Container(
                width: isWide ? 140 : 120,
                height: isWide ? 140 : 120,
                decoration: BoxDecoration(
                  color: data.color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(32),
                ),
                child: Center(
                  child: Text(data.emoji,
                      style: TextStyle(fontSize: isWide ? 68 : 56)),
                ),
              ),
              const SizedBox(height: 36),
              Text(
                data.title,
                style: TextStyle(
                  fontSize: isWide ? 38 : 32,
                  fontWeight: FontWeight.w900,
                  color: data.color,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                data.subtitle,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: data.color.withValues(alpha: 0.7),
                ),
              ),
              const SizedBox(height: 24),
              Text(
                data.body,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 15, height: 1.6, color: Color(0xFF374151)),
              ),

              // Store code field — only on last page
              if (data.isStorePage && storeCodeCtrl != null) ...[
                const SizedBox(height: 32),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Código de tienda (opcional)',
                    style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: data.color),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: storeCodeCtrl,
                  decoration: InputDecoration(
                    hintText: 'Ej: mercadona-madrid-001',
                    prefixIcon: const Icon(Icons.store_outlined, size: 18),
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12)),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide(color: data.color, width: 2),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    filled: true,
                    fillColor: Colors.white,
                  ),
                  style: const TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Tu responsable te facilitará este código. Puedes dejarlo vacío.',
                  style: TextStyle(fontSize: 11, color: Colors.grey),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PageData {
  final String emoji;
  final String title;
  final String subtitle;
  final String body;
  final Color color;
  final Color bgColor;
  final bool isStorePage;

  const _PageData({
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.body,
    required this.color,
    required this.bgColor,
    this.isStorePage = false,
  });
}
