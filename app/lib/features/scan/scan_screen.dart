import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_service.dart';
import '../../core/theme.dart';

final _scanResultProvider = StateProvider<String?>((ref) => null);
final _scanLoadingProvider = StateProvider<bool>((ref) => false);
final _lastBarcodeProvider = StateProvider<String?>((ref) => null);
final _cameraErrorProvider = StateProvider<String?>((ref) => null);

class ScanScreen extends ConsumerStatefulWidget {
  const ScanScreen({super.key});

  @override
  ConsumerState<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends ConsumerState<ScanScreen>
    with WidgetsBindingObserver {
  MobileScannerController? _controller;
  bool _cameraActive = true;
  bool _torchOn = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
  }

  void _initCamera() {
    _controller = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      facing: CameraFacing.back,
      torchEnabled: false,
    );
    ref.read(_cameraErrorProvider.notifier).state = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    if (state == AppLifecycleState.resumed && _cameraActive) {
      _controller?.start();
    } else if (state == AppLifecycleState.paused) {
      _controller?.stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _onBarcodeDetected(BarcodeCapture capture) async {
    final barcode = capture.barcodes.firstOrNull?.rawValue;
    if (barcode == null || barcode.isEmpty) return;
    if (ref.read(_scanLoadingProvider)) return;

    ref.read(_lastBarcodeProvider.notifier).state = barcode;
    ref.read(_scanLoadingProvider.notifier).state = true;
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_cameraErrorProvider.notifier).state = null;

    _controller?.stop();
    setState(() => _cameraActive = false);

    try {
      final response = await api.scan(barcode);
      final result = response['result'] as String? ?? 'Sin respuesta del servidor.';
      ref.read(_scanResultProvider.notifier).state = result;
    } on Exception catch (e) {
      final msg = e.toString();
      if (msg.contains('TimeoutException')) {
        ref.read(_scanResultProvider.notifier).state =
            'El análisis está tardando más de lo normal. '
            'Chuwi sigue procesando — intenta de nuevo en unos segundos.';
      } else if (msg.contains('SocketException') || msg.contains('Connection refused')) {
        ref.read(_scanResultProvider.notifier).state =
            'No se puede conectar con el servidor. '
            'Verifica que estás en la misma red WiFi que el backend.';
      } else {
        ref.read(_scanResultProvider.notifier).state = 'Error al analizar el producto: $e';
      }
    } finally {
      ref.read(_scanLoadingProvider.notifier).state = false;
    }
  }

  void _onCameraError(MobileScannerException error) {
    String message;
    switch (error.errorCode) {
      case MobileScannerErrorCode.permissionDenied:
        message = 'Permiso de cámara denegado.\n\n'
            'Ve a Ajustes → MermaOps → Permisos → Cámara y actívala.';
        break;
      case MobileScannerErrorCode.unsupported:
        message = 'Este dispositivo no tiene cámara trasera compatible.';
        break;
      default:
        message = 'Error de cámara: ${error.errorCode.name}. '
            'Reinicia la aplicación e inténtalo de nuevo.';
    }
    ref.read(_cameraErrorProvider.notifier).state = message;
    setState(() => _cameraActive = false);
  }

  void _resetScan() {
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_lastBarcodeProvider.notifier).state = null;
    ref.read(_cameraErrorProvider.notifier).state = null;
    if (_controller == null) _initCamera();
    _controller?.start();
    setState(() {
      _cameraActive = true;
      _torchOn = false;
    });
  }

  void _retryCamera() {
    _controller?.dispose();
    _initCamera();
    setState(() {
      _cameraActive = true;
      _torchOn = false;
    });
  }

  void _toggleTorch() {
    _controller?.toggleTorch();
    setState(() => _torchOn = !_torchOn);
  }

  @override
  Widget build(BuildContext context) {
    final result = ref.watch(_scanResultProvider);
    final loading = ref.watch(_scanLoadingProvider);
    final lastBarcode = ref.watch(_lastBarcodeProvider);
    final cameraError = ref.watch(_cameraErrorProvider);

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Escanear producto'),
        actions: [
          if (_cameraActive && cameraError == null)
            IconButton(
              icon: Icon(_torchOn ? Icons.flash_on : Icons.flash_off),
              onPressed: _toggleTorch,
              tooltip: _torchOn ? 'Apagar linterna' : 'Encender linterna',
            ),
          if (result != null || !_cameraActive || cameraError != null)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: cameraError != null ? _retryCamera : _resetScan,
              tooltip: 'Nuevo escaneo',
            ),
        ],
      ),
      body: Column(
        children: [
          // Camera viewport
          Expanded(
            flex: _cameraActive && cameraError == null ? 2 : 1,
            child: _CameraViewport(
              cameraActive: _cameraActive,
              cameraError: cameraError,
              lastBarcode: lastBarcode,
              controller: _controller,
              onDetect: _onBarcodeDetected,
              onError: _onCameraError,
              onRetry: _retryCamera,
            ),
          ),

          // Result / loading area
          if (loading || result != null || cameraError != null)
            Expanded(
              flex: 2,
              child: Container(
                color: Colors.white,
                child: loading
                    ? const _LoadingView()
                    : cameraError != null && result == null
                        ? _CameraPermissionError(
                            message: cameraError,
                            onRetry: _retryCamera,
                          )
                        : result != null
                            ? _ScanResult(result: result, onScanAgain: _resetScan)
                            : const SizedBox.shrink(),
              ),
            ),
        ],
      ),
    );
  }
}

// ── Camera viewport ───────────────────────────────────────────────────────────

class _CameraViewport extends StatelessWidget {
  final bool cameraActive;
  final String? cameraError;
  final String? lastBarcode;
  final MobileScannerController? controller;
  final void Function(BarcodeCapture) onDetect;
  final void Function(MobileScannerException) onError;
  final VoidCallback onRetry;

  const _CameraViewport({
    required this.cameraActive,
    required this.cameraError,
    required this.lastBarcode,
    required this.controller,
    required this.onDetect,
    required this.onError,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    if (cameraError != null) {
      return Container(
        color: Colors.black87,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.no_photography_outlined,
                  color: Colors.white54, size: 56),
              const SizedBox(height: 12),
              const Text(
                'Cámara no disponible',
                style: TextStyle(color: Colors.white70, fontSize: 14),
              ),
            ],
          ),
        ),
      );
    }

    if (!cameraActive) {
      return Container(
        color: Colors.black87,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.qr_code, color: Colors.white54, size: 48),
              const SizedBox(height: 8),
              Text(
                lastBarcode ?? '',
                style: const TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ],
          ),
        ),
      );
    }

    return Stack(
      children: [
        if (controller != null)
          MobileScanner(
            controller: controller!,
            onDetect: onDetect,
            errorBuilder: (context, error, child) {
              return Container(
                color: Colors.black87,
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline,
                          color: Colors.white60, size: 48),
                      const SizedBox(height: 8),
                      Text(
                        'Error: ${error.errorCode.name}',
                        style: const TextStyle(color: Colors.white60),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: onRetry,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Reintentar'),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),

        // Scan frame overlay
        Center(
          child: Container(
            width: 230,
            height: 230,
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF059669), width: 3),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Stack(
              children: [
                // Corner accents
                ..._corners(const Color(0xFF059669)),
              ],
            ),
          ),
        ),

        // Hint
        Positioned(
          bottom: 20,
          left: 0,
          right: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Text(
                'Centra el código de barras en el recuadro',
                style: TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
          ),
        ),
      ],
    );
  }

  static List<Widget> _corners(Color color) {
    const size = 20.0;
    const thickness = 3.0;
    return [
      // Top-left
      Positioned(top: 0, left: 0,
          child: _Corner(color: color, size: size, t: thickness,
              topLeft: true)),
      // Top-right
      Positioned(top: 0, right: 0,
          child: _Corner(color: color, size: size, t: thickness,
              topRight: true)),
      // Bottom-left
      Positioned(bottom: 0, left: 0,
          child: _Corner(color: color, size: size, t: thickness,
              bottomLeft: true)),
      // Bottom-right
      Positioned(bottom: 0, right: 0,
          child: _Corner(color: color, size: size, t: thickness,
              bottomRight: true)),
    ];
  }
}

class _Corner extends StatelessWidget {
  final Color color;
  final double size;
  final double t;
  final bool topLeft, topRight, bottomLeft, bottomRight;

  const _Corner({
    required this.color,
    required this.size,
    required this.t,
    this.topLeft = false,
    this.topRight = false,
    this.bottomLeft = false,
    this.bottomRight = false,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _CornerPainter(
          color: color, t: t,
          topLeft: topLeft, topRight: topRight,
          bottomLeft: bottomLeft, bottomRight: bottomRight,
        ),
      ),
    );
  }
}

class _CornerPainter extends CustomPainter {
  final Color color;
  final double t;
  final bool topLeft, topRight, bottomLeft, bottomRight;

  _CornerPainter({
    required this.color, required this.t,
    required this.topLeft, required this.topRight,
    required this.bottomLeft, required this.bottomRight,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color..strokeWidth = t..style = PaintingStyle.stroke;
    final path = Path();
    if (topLeft) {
      path.moveTo(0, size.height);
      path.lineTo(0, 0);
      path.lineTo(size.width, 0);
    }
    if (topRight) {
      path.moveTo(0, 0);
      path.lineTo(size.width, 0);
      path.lineTo(size.width, size.height);
    }
    if (bottomLeft) {
      path.moveTo(0, 0);
      path.lineTo(0, size.height);
      path.lineTo(size.width, size.height);
    }
    if (bottomRight) {
      path.moveTo(0, size.height);
      path.lineTo(size.width, size.height);
      path.lineTo(size.width, 0);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_CornerPainter old) => false;
}

// ── Loading view ──────────────────────────────────────────────────────────────

class _LoadingView extends StatelessWidget {
  const _LoadingView();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: Color(0xFF059669)),
          SizedBox(height: 16),
          Text(
            'Chuwi está analizando el producto...',
            style: TextStyle(fontSize: 14, color: Color(0xFF6B7280)),
          ),
          SizedBox(height: 4),
          Text(
            'Puede tardar hasta 15 segundos',
            style: TextStyle(fontSize: 12, color: Color(0xFF9CA3AF)),
          ),
        ],
      ),
    );
  }
}

// ── Camera permission error ───────────────────────────────────────────────────

class _CameraPermissionError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _CameraPermissionError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.camera_alt_outlined, size: 56, color: Color(0xFF9CA3AF)),
          const SizedBox(height: 16),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 14, color: Color(0xFF374151), height: 1.6),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Reintentar'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF059669),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Scan result ───────────────────────────────────────────────────────────────

class _ScanResult extends StatelessWidget {
  final String result;
  final VoidCallback onScanAgain;

  const _ScanResult({required this.result, required this.onScanAgain});

  @override
  Widget build(BuildContext context) {
    final isError = result.startsWith('Error') ||
        result.startsWith('No se puede') ||
        result.startsWith('El análisis') ||
        result.startsWith('Producto no encontrado');
    final hasCritical = result.contains('CRÍTICO') || result.contains('RETIRAR');
    final hasDiscount = result.contains('REBAJAR') || result.contains('%');

    Color headerColor = const Color(0xFF059669);
    if (isError) {
      headerColor = Colors.grey;
    } else if (hasCritical) {
      headerColor = UrgencyColors.critical;
    } else if (hasDiscount) {
      headerColor = UrgencyColors.high;
    }

    IconData headerIcon = Icons.check_circle_outline;
    String headerLabel = 'Análisis completado';
    if (isError) {
      headerIcon = Icons.wifi_off_outlined;
      headerLabel = 'Error de conexión';
    } else if (hasCritical) {
      headerIcon = Icons.warning_amber_rounded;
      headerLabel = 'Acción urgente requerida';
    } else if (hasDiscount) {
      headerIcon = Icons.sell_outlined;
      headerLabel = 'Rebajar precio';
    }

    return Column(
      children: [
        // Handle
        Container(
          margin: const EdgeInsets.only(top: 8, bottom: 4),
          width: 36, height: 4,
          decoration: BoxDecoration(
            color: Colors.grey[300],
            borderRadius: BorderRadius.circular(2),
          ),
        ),

        // Header
        Container(
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: headerColor.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: headerColor.withValues(alpha: 0.3)),
          ),
          child: Row(
            children: [
              Icon(headerIcon, color: headerColor, size: 18),
              const SizedBox(width: 8),
              Text(
                headerLabel,
                style: TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w600, color: headerColor,
                ),
              ),
            ],
          ),
        ),

        // Result text
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: SelectableText(
              result,
              style: const TextStyle(
                fontSize: 14, height: 1.6, color: Color(0xFF1F2937),
              ),
            ),
          ),
        ),

        // Actions
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.copy, size: 16),
                  label: const Text('Copiar'),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: result));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Resultado copiado'),
                          duration: Duration(seconds: 2),
                        ),
                      );
                    }
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.qr_code_scanner, size: 16),
                  label: const Text('Escanear otro'),
                  onPressed: onScanAgain,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF059669),
                    foregroundColor: Colors.white,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
