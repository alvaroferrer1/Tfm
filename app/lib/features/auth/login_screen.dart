import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../core/api_service.dart';
import '../../core/supabase_client.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _confirmPassCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();

  bool _loading = false;
  String? _error;
  String? _success;
  bool _obscurePass = true;
  bool _obscureConfirm = true;
  bool _isRegister = false;

  late AnimationController _animCtrl;
  late Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 250),
    );
    _fadeAnim = CurvedAnimation(parent: _animCtrl, curve: Curves.easeIn);
    _animCtrl.forward();
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    _confirmPassCtrl.dispose();
    _nameCtrl.dispose();
    _animCtrl.dispose();
    super.dispose();
  }

  // ── Validaciones ──────────────────────────────────────────────────────────

  String? _validateEmail(String email) {
    if (email.isEmpty) return 'Introduce tu email.';
    if (!email.contains('@')) return 'El email debe contener @.';
    final parts = email.split('@');
    if (parts.length != 2 || parts[0].isEmpty || !parts[1].contains('.')) {
      return 'Email no válido (ej: nombre@dominio.com).';
    }
    return null;
  }

  String? _validatePassword(String pass) {
    if (pass.isEmpty) return 'Introduce tu contraseña.';
    if (pass.length < 6) return 'La contraseña debe tener al menos 6 caracteres.';
    return null;
  }

  String? _validateForm() {
    final email = _emailCtrl.text.trim();
    final pass = _passCtrl.text;

    if (_isRegister && _nameCtrl.text.trim().isEmpty) {
      return 'Introduce tu nombre completo.';
    }
    final emailErr = _validateEmail(email);
    if (emailErr != null) return emailErr;

    final passErr = _validatePassword(pass);
    if (passErr != null) return passErr;

    if (_isRegister && _confirmPassCtrl.text != pass) {
      return 'Las contraseñas no coinciden.';
    }
    return null;
  }

  // ── Acciones ──────────────────────────────────────────────────────────────

  Future<void> _submit() async {
    final err = _validateForm();
    if (err != null) {
      setState(() => _error = err);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _success = null;
    });
    try {
      if (_isRegister) {
        await _register();
      } else {
        await _login();
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _quickLogin(String email, String password) {
    _emailCtrl.text = email;
    _passCtrl.text = password;
    setState(() {
      _isRegister = false;
      _error = null;
      _success = null;
    });
    _submit();
  }

  Future<void> _login() async {
    try {
      await supabase.auth.signInWithPassword(
        email: _emailCtrl.text.trim(),
        password: _passCtrl.text,
      );
      api.notifyAppLogin();
      // Detectar rol y mostrar bienvenida antes de navegar
      String roleLabel = 'usuario';
      try {
        final profile = await api.getCurrentUser();
        final role = profile['role'] as String? ?? 'staff';
        roleLabel = {'manager': 'Supervisor', 'admin': 'Admin'}[role] ?? 'Encargado';
      } catch (_) {}
      if (mounted) {
        setState(() {
          _success = 'Sesión iniciada como $roleLabel. Cargando...';
        });
        await Future.delayed(const Duration(milliseconds: 1100));
        if (mounted) context.go('/');
      }
    } on AuthException catch (e) {
      setState(() => _error = _translateError(e.message));
    } catch (_) {
      setState(() => _error = 'Error de conexión. Comprueba tu internet.');
    }
  }

  Future<void> _register() async {
    try {
      final res = await supabase.auth.signUp(
        email: _emailCtrl.text.trim(),
        password: _passCtrl.text,
        data: {
          'full_name': _nameCtrl.text.trim(),
          'role': 'staff',
        },
      );
      if (res.session != null) {
        // Confirmación de email desactivada en Supabase → sesión inmediata
        api.notifyAppLogin();
        if (mounted) context.go('/');
      } else {
        setState(() {
          _success =
              'Cuenta creada. Revisa tu email para confirmar la cuenta y después inicia sesión.';
          _isRegister = false;
        });
      }
    } on AuthException catch (e) {
      setState(() => _error = _translateError(e.message));
    } catch (_) {
      setState(() => _error = 'Error de conexión. Comprueba tu internet.');
    }
  }

  String _translateError(String msg) {
    if (msg.contains('Invalid login credentials')) {
      return 'Email o contraseña incorrectos.';
    }
    if (msg.contains('Email not confirmed')) {
      return 'Revisa tu bandeja de entrada — te enviamos un email de confirmación.';
    }
    if (msg.contains('User already registered') || msg.contains('already registered')) {
      return 'Ya existe una cuenta con ese email. Pulsa "Iniciar sesión" abajo.';
    }
    if (msg.contains('Password should be') || msg.contains('weak_password')) {
      return 'La contraseña debe tener al menos 6 caracteres.';
    }
    if (msg.contains('Unable to validate') || msg.contains('invalid_email') || msg.contains('not valid')) {
      return 'El email no tiene un formato válido.';
    }
    if (msg.contains('over_email_send_rate_limit') ||
        msg.contains('rate limit') ||
        msg.contains('too many') ||
        msg.contains('For security purposes')) {
      return 'Demasiados intentos. Espera 5 minutos e inténtalo de nuevo.';
    }
    if (msg.contains('signup_disabled')) {
      return 'El registro está desactivado. Contacta al administrador.';
    }
    if (msg.contains('network') || msg.contains('connection') || msg.contains('SocketException')) {
      return 'Sin conexión. Comprueba tu internet e inténtalo de nuevo.';
    }
    // No exponer detalles internos al usuario — siempre mensaje genérico
    return 'Error de autenticación. Inténtalo de nuevo o contacta al administrador.';
  }

  void _toggleMode() {
    setState(() {
      _isRegister = !_isRegister;
      _error = null;
      _success = null;
    });
    _animCtrl.forward(from: 0);
  }

  void _showForgotPassword() {
    final emailCtrl = TextEditingController(text: _emailCtrl.text.trim());
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(children: [
          Icon(Icons.lock_reset_outlined, color: Color(0xFF059669), size: 22),
          SizedBox(width: 8),
          Text('Recuperar contraseña', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text(
            'Introduce tu email y te enviaremos un enlace para restablecer tu contraseña.',
            style: TextStyle(fontSize: 13, color: Color(0xFF6B7280)),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: emailCtrl,
            keyboardType: TextInputType.emailAddress,
            autofocus: true,
            decoration: InputDecoration(
              labelText: 'Email',
              prefixIcon: const Icon(Icons.email_outlined, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            ),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancelar', style: TextStyle(color: Color(0xFF6B7280))),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF059669),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              elevation: 0,
            ),
            onPressed: () async {
              final email = emailCtrl.text.trim();
              if (email.isEmpty || !email.contains('@')) return;
              Navigator.of(ctx).pop();
              try {
                await supabase.auth.resetPasswordForEmail(email);
                if (mounted) {
                  setState(() => _success = 'Email enviado a $email. Revisa tu bandeja de entrada.');
                }
              } catch (_) {
                if (mounted) {
                  setState(() => _error = 'No se pudo enviar el email. Comprueba la dirección.');
                }
              }
            },
            child: const Text('Enviar enlace', style: TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }

  // ── UI ────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF0FDF4),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── Logo ──────────────────────────────────────────────────
                  Center(
                    child: Column(
                      children: [
                        Container(
                          width: 80,
                          height: 80,
                          decoration: BoxDecoration(
                            color: const Color(0xFF059669),
                            borderRadius: BorderRadius.circular(22),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF059669).withValues(alpha: 0.3),
                                blurRadius: 20,
                                offset: const Offset(0, 6),
                              ),
                            ],
                          ),
                          child: const Center(
                            child: Text('🌱', style: TextStyle(fontSize: 40)),
                          ),
                        ),
                        const SizedBox(height: 14),
                        const Text(
                          'MermaOps',
                          style: TextStyle(
                            fontSize: 30,
                            fontWeight: FontWeight.w900,
                            color: Color(0xFF059669),
                            letterSpacing: -1,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Gestión inteligente de merma',
                          style: TextStyle(fontSize: 13, color: Colors.grey[500]),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 36),

                  // ── Tarjeta principal ─────────────────────────────────────
                  FadeTransition(
                    opacity: _fadeAnim,
                    child: Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.06),
                            blurRadius: 24,
                            offset: const Offset(0, 6),
                          ),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          // Título con icono
                          Row(
                            children: [
                              Icon(
                                _isRegister
                                    ? Icons.person_add_outlined
                                    : Icons.login_outlined,
                                color: const Color(0xFF059669),
                                size: 22,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                _isRegister ? 'Crear cuenta' : 'Iniciar sesión',
                                style: const TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 22),

                          // Nombre (solo en registro)
                          if (_isRegister) ...[
                            _FormField(
                              controller: _nameCtrl,
                              label: 'Nombre completo',
                              icon: Icons.badge_outlined,
                              inputAction: TextInputAction.next,
                              capitalization: TextCapitalization.words,
                            ),
                            const SizedBox(height: 14),
                          ],

                          // Email
                          _FormField(
                            controller: _emailCtrl,
                            label: 'Email',
                            icon: Icons.email_outlined,
                            keyboard: TextInputType.emailAddress,
                            inputAction: TextInputAction.next,
                          ),
                          const SizedBox(height: 14),

                          // Contraseña
                          _PasswordField(
                            controller: _passCtrl,
                            label: 'Contraseña',
                            obscure: _obscurePass,
                            onToggle: () =>
                                setState(() => _obscurePass = !_obscurePass),
                            inputAction: _isRegister
                                ? TextInputAction.next
                                : TextInputAction.done,
                            onSubmitted:
                                _isRegister ? null : (_) => _submit(),
                            onChanged: _isRegister
                                ? (_) => setState(() {})
                                : null,
                          ),

                          // Olvidé mi contraseña (solo en login)
                          if (!_isRegister) ...[
                            const SizedBox(height: 4),
                            Align(
                              alignment: Alignment.centerRight,
                              child: TextButton(
                                onPressed: _showForgotPassword,
                                style: TextButton.styleFrom(
                                  minimumSize: Size.zero,
                                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                ),
                                child: const Text(
                                  '¿Olvidaste tu contraseña?',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Color(0xFF059669),
                                  ),
                                ),
                              ),
                            ),
                          ],

                          // Confirmar contraseña (solo en registro)
                          if (_isRegister) ...[
                            const SizedBox(height: 14),
                            _PasswordField(
                              controller: _confirmPassCtrl,
                              label: 'Confirmar contraseña',
                              obscure: _obscureConfirm,
                              onToggle: () => setState(
                                  () => _obscureConfirm = !_obscureConfirm),
                              inputAction: TextInputAction.done,
                              onSubmitted: (_) => _submit(),
                            ),
                          ],

                          // Indicador de fuerza de contraseña (registro)
                          if (_isRegister) ...[
                            const SizedBox(height: 8),
                            _PasswordStrength(password: _passCtrl.text),
                          ],

                          // Error
                          if (_error != null) ...[
                            const SizedBox(height: 14),
                            _Banner(
                              text: _error!,
                              isError: true,
                            ),
                          ],

                          // Éxito
                          if (_success != null) ...[
                            const SizedBox(height: 14),
                            _Banner(text: _success!, isError: false),
                          ],

                          const SizedBox(height: 22),

                          // Botón principal
                          SizedBox(
                            height: 50,
                            child: ElevatedButton(
                              onPressed: _loading ? null : _submit,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF059669),
                                foregroundColor: Colors.white,
                                elevation: 0,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              child: _loading
                                  ? const SizedBox(
                                      height: 20,
                                      width: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white,
                                      ),
                                    )
                                  : Text(
                                      _isRegister
                                          ? 'Crear cuenta'
                                          : 'Entrar',
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
                  ),

                  const SizedBox(height: 20),

                  // ── Toggle login/registro ─────────────────────────────────
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        _isRegister
                            ? '¿Ya tienes cuenta? '
                            : '¿No tienes cuenta? ',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.grey[600],
                        ),
                      ),
                      GestureDetector(
                        onTap: _toggleMode,
                        child: Text(
                          _isRegister ? 'Iniciar sesión' : 'Crear cuenta',
                          style: const TextStyle(
                            fontSize: 14,
                            color: Color(0xFF059669),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 28),

                  // ── Acceso rápido demo TFM ────────────────────────────────
                  if (!_isRegister) ...[
                    Row(
                      children: [
                        Expanded(child: Divider(color: Colors.grey[300])),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 10),
                          child: Text(
                            'Acceso rápido — Demo',
                            style: TextStyle(fontSize: 11, color: Colors.grey[500]),
                          ),
                        ),
                        Expanded(child: Divider(color: Colors.grey[300])),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: _QuickLoginButton(
                            label: 'Encargado',
                            icon: Icons.store_outlined,
                            color: const Color(0xFF059669),
                            onTap: () => _quickLogin(
                                'encargado@mermaops.es', 'Encargado2024!'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _QuickLoginButton(
                            label: 'Demo',
                            icon: Icons.manage_accounts_outlined,
                            color: const Color(0xFF2563EB),
                            onTap: () => _quickLogin(
                                'demo@mermaops.es', 'Demo2024!'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _QuickLoginButton(
                            label: 'Admin',
                            icon: Icons.admin_panel_settings_outlined,
                            color: const Color(0xFF7C3AED),
                            onTap: () => _quickLogin(
                                'admin@mermaops.es', 'Admin2024!'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],

                  const SizedBox(height: 16),

                  // ── Footer ────────────────────────────────────────────────
                  Center(
                    child: Column(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: const Color(0xFFD1FAE5),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.store_outlined,
                                  size: 14, color: Color(0xFF059669)),
                              SizedBox(width: 5),
                              Text(
                                'Super Martínez — Demo TFM',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Color(0xFF065F46),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'MermaOps · IA para reducción de merma',
                          style: TextStyle(
                              fontSize: 10, color: Colors.grey[400]),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ── Widgets auxiliares ────────────────────────────────────────────────────────

class _FormField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final IconData icon;
  final TextInputType keyboard;
  final TextInputAction inputAction;
  final TextCapitalization capitalization;

  const _FormField({
    required this.controller,
    required this.label,
    required this.icon,
    this.keyboard = TextInputType.text,
    this.inputAction = TextInputAction.next,
    this.capitalization = TextCapitalization.none,
  });

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: keyboard,
      textInputAction: inputAction,
      textCapitalization: capitalization,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, size: 20),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      ),
    );
  }
}

class _PasswordField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final bool obscure;
  final VoidCallback onToggle;
  final TextInputAction inputAction;
  final void Function(String)? onSubmitted;
  final void Function(String)? onChanged;

  const _PasswordField({
    required this.controller,
    required this.label,
    required this.obscure,
    required this.onToggle,
    this.inputAction = TextInputAction.done,
    this.onSubmitted,
    this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      textInputAction: inputAction,
      onSubmitted: onSubmitted,
      onChanged: onChanged,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: const Icon(Icons.lock_outlined, size: 20),
        suffixIcon: IconButton(
          icon: Icon(
            obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
            size: 20,
          ),
          onPressed: onToggle,
        ),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      ),
    );
  }
}

class _PasswordStrength extends StatelessWidget {
  final String password;
  const _PasswordStrength({required this.password});

  int _score() {
    int s = 0;
    if (password.length >= 6) s++;
    if (password.length >= 10) s++;
    if (RegExp(r'[A-Z]').hasMatch(password)) s++;
    if (RegExp(r'[0-9]').hasMatch(password)) s++;
    if (RegExp(r'[^A-Za-z0-9]').hasMatch(password)) s++;
    return s;
  }

  String _label(int s) {
    if (s <= 1) return 'Muy débil';
    if (s == 2) return 'Débil';
    if (s == 3) return 'Aceptable';
    if (s == 4) return 'Fuerte';
    return 'Muy fuerte';
  }

  Color _color(int s) {
    if (s <= 1) return const Color(0xFFEF4444);
    if (s == 2) return const Color(0xFFF97316);
    if (s == 3) return const Color(0xFFD97706);
    if (s == 4) return const Color(0xFF22C55E);
    return const Color(0xFF059669);
  }

  @override
  Widget build(BuildContext context) {
    if (password.isEmpty) return const SizedBox.shrink();
    final s = _score();
    final label = _label(s);
    final color = _color(s);
    return Row(
      children: [
        Expanded(
          child: LinearProgressIndicator(
            value: s / 5,
            backgroundColor: const Color(0xFFF3F4F6),
            valueColor: AlwaysStoppedAnimation<Color>(color),
            minHeight: 4,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 8),
        Text(label,
            style: TextStyle(
                fontSize: 11, color: color, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _QuickLoginButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _QuickLoginButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.07),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 20, color: color),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  final String text;
  final bool isError;
  const _Banner({required this.text, required this.isError});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isError ? const Color(0xFFFEF2F2) : const Color(0xFFF0FDF4),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isError
              ? const Color(0xFFFCA5A5)
              : const Color(0xFF6EE7B7),
        ),
      ),
      child: Row(
        children: [
          Icon(
            isError ? Icons.error_outline : Icons.check_circle_outline,
            color: isError ? const Color(0xFFB91C1C) : const Color(0xFF059669),
            size: 18,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: isError
                    ? const Color(0xFFB91C1C)
                    : const Color(0xFF065F46),
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
