import 'package:flutter/material.dart';

/// Banner de error no-bloqueante (aparece encima del contenido, no un dialog).
/// Muestra botón Reintentar si se proporciona onRetry.
class ErrorBanner extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;

  const ErrorBanner({required this.error, this.onRetry, super.key});

  @override
  Widget build(BuildContext context) {
    final isNetwork = () {
      final s = error.toString().toLowerCase();
      return s.contains('connection') ||
          s.contains('socket') ||
          s.contains('refused') ||
          s.contains('timeout');
    }();

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isNetwork
            ? const Color(0xFFEFF6FF)
            : Theme.of(context).colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isNetwork
              ? const Color(0xFF2563EB)
              : Theme.of(context).colorScheme.error.withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        children: [
          Icon(
            isNetwork ? Icons.wifi_off_rounded : Icons.warning_amber_rounded,
            color: isNetwork
                ? const Color(0xFF856404)
                : Theme.of(context).colorScheme.error,
            size: 18,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              isNetwork
                  ? 'Sin conexión. Mostrando datos guardados.'
                  : 'Error al cargar. Pulsa reintentar.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          if (onRetry != null)
            TextButton(
              onPressed: onRetry,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                minimumSize: Size.zero,
              ),
              child: const Text('Reintentar'),
            ),
        ],
      ),
    );
  }
}

/// Convierte una excepción en mensaje amigable para el usuario.
String friendlyError(Object? e) {
  final msg = e?.toString().toLowerCase() ?? '';
  if (msg.contains('timeout') || msg.contains('timeoutexception')) {
    return 'La operación tardó demasiado. Inténtalo de nuevo.';
  }
  if (msg.contains('clientexception') || msg.contains('failed host') ||
      msg.contains('effectiveuri') || msg.contains('connection') ||
      msg.contains('socket') || msg.contains('refused') || msg.contains('network')) {
    return 'Sin conexión con el servidor. Comprueba que el backend está corriendo.';
  }
  if (msg.contains('401') || msg.contains('403') || msg.contains('unauthorized')) {
    return 'Sesión caducada. Vuelve a iniciar sesión.';
  }
  if (msg.contains('404') || msg.contains('not found')) {
    return 'No se encontraron datos. El sistema puede no tener información aún.';
  }
  if (msg.contains('500') || msg.contains('server error')) {
    return 'Error del servidor. Inténtalo de nuevo en unos segundos.';
  }
  return 'No se pudo completar la operación. Inténtalo de nuevo.';
}

/// Widget de error estándar para estados de error en pantallas.
class AppErrorWidget extends StatelessWidget {
  final Object? error;
  final VoidCallback? onRetry;
  final String? customMessage;

  const AppErrorWidget({super.key, this.error, this.onRetry, this.customMessage});

  @override
  Widget build(BuildContext context) {
    final isNetwork = () {
      final s = error?.toString().toLowerCase() ?? '';
      return s.contains('connection') || s.contains('socket') ||
          s.contains('refused') || s.contains('timeout');
    }();
    final msg = customMessage ?? (isNetwork
        ? 'Sin conexión con el servidor. Comprueba que el backend está activo.'
        : friendlyError(error));
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(isNetwork ? Icons.cloud_off_rounded : Icons.warning_amber_rounded,
                size: 40, color: isNetwork ? Colors.grey : const Color(0xFFEF4444)),
            const SizedBox(height: 12),
            Text(msg,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 14, color: Color(0xFF374151), height: 1.5)),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Reintentar'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
