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
  int _page = 0;

  static const _pages = [_PageData(
    emoji: '🧠',
    title: 'MermaOps',
    subtitle: 'El problema que resuelve',
    body:
        'El desperdicio alimentario cuesta a un supermercado entre el 2% y el 5% de sus ingresos cada año.\n\n'
        'MermaOps usa inteligencia artificial para detectar qué productos están en riesgo, '
        'decidir qué hacer con ellos y guiar al personal — en tiempo real, sin hardware adicional.',
    color: Color(0xFF059669),
    bgColor: Color(0xFFF0FDF4),
  ), _PageData(
    emoji: '⚡',
    title: 'Kuine',
    subtitle: 'El orquestador inteligente',
    body:
        'Kuine analiza toda la tienda cada mañana a las 7:30 con 25 herramientas de IA.\n\n'
        'Evalúa cada lote, calcula descuentos exactos, propone donaciones al banco de alimentos '
        'y genera el brief diario con trazabilidad completa.\n\n'
        'Funciona solo. Sin que nadie se lo pida.',
    color: Color(0xFF7C3AED),
    bgColor: Color(0xFFF5F3FF),
  ), _PageData(
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
  )];

  void _finish() {
    debugPrint('[onboarding] _finish() called — mounted=$mounted');
    SharedPreferences.getInstance()
        .then((prefs) => prefs.setBool('onboarding_done', true));
    if (mounted) {
      debugPrint('[onboarding] calling context.go(/login)');
      try {
        context.go('/login');
        debugPrint('[onboarding] context.go(/login) done');
      } catch (e, st) {
        debugPrint('[onboarding] ERROR: $e\n$st');
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _pages[_page].bgColor,
      body: SafeArea(
        child: Column(
          children: [
            // Skip button
            Align(
              alignment: Alignment.topRight,
              child: TextButton(
                onPressed: _finish,
                child: Text(
                  'Saltar',
                  style: TextStyle(
                    color: _pages[_page].color.withValues(alpha: 0.7),
                    fontSize: 14,
                  ),
                ),
              ),
            ),

            // Page content
            Expanded(
              child: PageView.builder(
                controller: _controller,
                onPageChanged: (i) => setState(() => _page = i),
                itemCount: _pages.length,
                itemBuilder: (context, i) => _OnboardingPage(data: _pages[i]),
              ),
            ),

            // Dots + button
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 0, 32, 40),
              child: Column(
                children: [
                  // Dot indicators
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(_pages.length, (i) {
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 250),
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        width: i == _page ? 24 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: i == _page
                              ? _pages[_page].color
                              : _pages[_page].color.withValues(alpha: 0.25),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 28),

                  // Action button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _pages[_page].color,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        elevation: 0,
                      ),
                      onPressed: () {
                        if (_page < _pages.length - 1) {
                          _controller.nextPage(
                            duration: const Duration(milliseconds: 350),
                            curve: Curves.easeInOut,
                          );
                        } else {
                          _finish();
                        }
                      },
                      child: Text(
                        _page < _pages.length - 1 ? 'Siguiente' : 'Empezar',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OnboardingPage extends StatelessWidget {
  final _PageData data;
  const _OnboardingPage({required this.data});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Big emoji icon
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              color: data.color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(32),
            ),
            child: Center(
              child: Text(data.emoji, style: const TextStyle(fontSize: 56)),
            ),
          ),
          const SizedBox(height: 36),

          // Title
          Text(
            data.title,
            style: TextStyle(
              fontSize: 32,
              fontWeight: FontWeight.w900,
              color: data.color,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 6),

          // Subtitle
          Text(
            data.subtitle,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: data.color.withValues(alpha: 0.7),
            ),
          ),
          const SizedBox(height: 24),

          // Body
          Text(
            data.body,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 15,
              height: 1.6,
              color: Color(0xFF374151),
            ),
          ),
        ],
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

  const _PageData({
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.body,
    required this.color,
    required this.bgColor,
  });
}
