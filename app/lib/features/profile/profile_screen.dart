import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_service.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';

final _userProfileProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return api.getCurrentUser();
});

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _tgController = TextEditingController();
  bool _linking = false;
  bool _unlinking = false;

  @override
  void dispose() {
    _tgController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profileAsync = ref.watch(_userProfileProvider);
    final user = supabase.auth.currentUser;

    return Scaffold(
      backgroundColor: const Color(0xFFF0FDF4),
      appBar: AppBar(
        title: const Text('Mi perfil'),
      ),
      body: profileAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _ErrorBody(error: '$e', onRetry: () => ref.invalidate(_userProfileProvider)),
        data: (profile) => ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // Avatar y datos básicos
            Center(
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 36,
                    backgroundColor: const Color(0xFF059669).withValues(alpha: 0.15),
                    child: Text(
                      (user?.email?.isNotEmpty == true)
                          ? user!.email![0].toUpperCase()
                          : '?',
                      style: const TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF059669),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    user?.email ?? 'Sin email',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFD1FAE5),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      (profile['role'] as String? ?? 'staff').toUpperCase(),
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF059669),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // Sección Telegram
            const Text(
              'Vincular con Telegram',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: (profile['telegram_linked'] as bool? ?? false)
                      ? const Color(0xFF059669)
                      : const Color(0xFFE5E7EB),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (profile['telegram_linked'] as bool? ?? false) ...[
                    Row(
                      children: [
                        const Icon(Icons.check_circle, color: Color(0xFF059669), size: 20),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Text(
                            'Cuenta de Telegram vinculada',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF059669),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Chuwi te reconoce en Telegram por tu nombre y rol. '
                      'Puedes hablarle directamente en lenguaje natural.',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        icon: _unlinking
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.link_off, size: 16),
                        label: const Text('Desvincular Telegram'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.red,
                          side: const BorderSide(color: Colors.red),
                        ),
                        onPressed: _unlinking ? null : () => _unlink(context),
                      ),
                    ),
                  ] else ...[
                    const Text(
                      'Cómo vincular:',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 8),
                    const _Step(
                      number: '1',
                      text: 'Abre Telegram y busca el bot de MermaOps (Chuwi)',
                    ),
                    const _Step(
                      number: '2',
                      text: 'Escribe /start — Chuwi te mostrará tu ID numérico',
                    ),
                    const _Step(
                      number: '3',
                      text: 'Copia ese número y pégalo aquí abajo',
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _tgController,
                      keyboardType: TextInputType.number,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      decoration: InputDecoration(
                        labelText: 'Tu ID de Telegram (solo números)',
                        hintText: '123456789',
                        prefixIcon: const Icon(Icons.telegram),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        filled: true,
                        fillColor: const Color(0xFFF9FAFB),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        icon: _linking
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.link, size: 18),
                        label: const Text('Vincular con Telegram'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF059669),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
                        onPressed: _linking ? null : () => _link(context),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Info section
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFF0F9FF),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFBAE6FD)),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, color: Color(0xFF0284C7), size: 18),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Al vincular tu Telegram, el agente Chuwi sabrá quién eres, '
                      'tu rol en la tienda y podrá responderte con contexto personalizado. '
                      'Los encargados tienen acceso a funciones adicionales.',
                      style: TextStyle(fontSize: 12, color: Color(0xFF0C4A6E)),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Cerrar sesión
            OutlinedButton.icon(
              icon: const Icon(Icons.logout),
              label: const Text('Cerrar sesión'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.red,
                side: const BorderSide(color: Colors.red),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              onPressed: () async {
                await supabase.auth.signOut();
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _link(BuildContext context) async {
    final id = _tgController.text.trim();
    if (id.isEmpty || int.tryParse(id) == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Introduce un ID de Telegram válido (solo números)'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _linking = true);
    try {
      await api.linkTelegram(id);
      ref.invalidate(_userProfileProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Telegram vinculado. Escribe /start a Chuwi para probar.'),
            backgroundColor: Color(0xFF059669),
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _linking = false);
    }
  }

  Future<void> _unlink(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Desvincular Telegram'),
        content: const Text(
          'Chuwi dejará de reconocerte. '
          'Puedes volver a vincularlo en cualquier momento.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Desvincular', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _unlinking = true);
    try {
      await api.unlinkTelegram();
      ref.invalidate(_userProfileProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Telegram desvinculado.')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _unlinking = false);
    }
  }
}

class _Step extends StatelessWidget {
  final String number;
  final String text;
  const _Step({required this.number, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 22,
            height: 22,
            decoration: BoxDecoration(
              color: const Color(0xFF059669),
              borderRadius: BorderRadius.circular(11),
            ),
            child: Center(
              child: Text(
                number,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: const TextStyle(fontSize: 13)),
          ),
        ],
      ),
    );
  }
}

class _ErrorBody extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;
  const _ErrorBody({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('No se pudo cargar el perfil',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(error,
                style: const TextStyle(fontSize: 12, color: Colors.grey),
                textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: onRetry, child: const Text('Reintentar')),
          ],
        ),
      ),
    );
  }
}
