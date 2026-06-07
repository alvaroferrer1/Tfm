import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
// Haptic feedback importado via flutter/services.dart (HapticFeedback)

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';

final _scanResultProvider = StateProvider<String?>((ref) => null);
final _scanLoadingProvider = StateProvider<bool>((ref) => false);
final _lastBarcodeProvider = StateProvider<String?>((ref) => null);
final _cameraErrorProvider = StateProvider<String?>((ref) => null);
final _scanDataProvider = StateProvider<Map<String, dynamic>?>((ref) => null);

// ── Batch scan mode ───────────────────────────────────────────────────────────
// Escanea múltiples productos seguidos y muestra todos los resultados en lista.
final _batchModeProvider = StateProvider<bool>((ref) => false);
final _batchResultsProvider = StateProvider<List<Map<String, dynamic>>>((ref) => []);

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
    if (!kIsWeb) _initCamera();
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
    ref.read(_scanDataProvider.notifier).state = null;

    // Haptic: código detectado
    HapticFeedback.mediumImpact();

    _controller?.stop();
    setState(() => _cameraActive = false);

    try {
      final response = await api.scan(barcode);
      final result = response['result'] as String? ?? 'Sin respuesta del servidor.';
      ref.read(_scanResultProvider.notifier).state = result;
      ref.read(_scanDataProvider.notifier).state = response;

      // Haptic: resultado recibido — urgencia por tipo
      final score = response['priority_score'] as int? ?? 0;
      if (score >= 85) {
        HapticFeedback.heavyImpact(); // crítico
      } else if (score >= 65) {
        HapticFeedback.mediumImpact(); // alto
      } else {
        HapticFeedback.lightImpact(); // normal
      }
    } catch (e) {
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
        ref.read(_scanResultProvider.notifier).state =
            'Error inesperado: ${msg.length > 80 ? msg.substring(0, 80) : msg}';
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
        message = 'No se pudo inicializar la cámara. '
            'Reinicia la aplicación e inténtalo de nuevo.';
    }
    ref.read(_cameraErrorProvider.notifier).state = message;
    setState(() => _cameraActive = false);
  }

  void _resetScan() {
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_lastBarcodeProvider.notifier).state = null;
    ref.read(_cameraErrorProvider.notifier).state = null;
    ref.read(_scanDataProvider.notifier).state = null;
    if (_controller == null) _initCamera();
    final cameraReady = _controller != null;
    if (cameraReady) _controller!.start();
    setState(() {
      _cameraActive = cameraReady;
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

  Future<void> _analyzeBarcode(String barcode) async {
    if (barcode.isEmpty || ref.read(_scanLoadingProvider)) return;
    ref.read(_lastBarcodeProvider.notifier).state = barcode;
    ref.read(_scanLoadingProvider.notifier).state = true;
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_scanDataProvider.notifier).state = null;
    try {
      final response = await api.scan(barcode);
      ref.read(_scanResultProvider.notifier).state =
          response['result'] as String? ?? 'Sin respuesta del servidor.';
      ref.read(_scanDataProvider.notifier).state = response;
    } catch (e) {
      ref.read(_scanResultProvider.notifier).state = friendlyError(e);
    } finally {
      ref.read(_scanLoadingProvider.notifier).state = false;
    }
  }

  Future<void> _analyzePhoto({ImageSource source = ImageSource.camera}) async {
    if (ref.read(_scanLoadingProvider)) return;
    final picker = ImagePicker();
    final picked = await picker.pickImage(
      source: source,
      maxWidth: 1200,
      imageQuality: 85,
    );
    if (picked == null) return;

    ref.read(_scanLoadingProvider.notifier).state = true;
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_lastBarcodeProvider.notifier).state = '📷 Foto';
    _controller?.stop();
    setState(() => _cameraActive = false);

    try {
      final bytes = await picked.readAsBytes();
      final base64Image = base64Encode(bytes);
      final result = await api.analyzeProductImage(imageBase64: base64Image);
      final estado = result['estado'] as String? ?? '';
      final accion = result['accion_recomendada'] as String? ?? '';
      final razon = result['razonamiento'] as String? ?? '';
      final confianza = result['confianza_pct'];
      final fechaVisible = result['fecha_visible'] as String? ?? '';
      final sb = StringBuffer();
      if (estado.isNotEmpty) sb.writeln('Estado: ${estado.toUpperCase()}');
      if (confianza != null) sb.writeln('Confianza: $confianza%');
      if (accion.isNotEmpty) sb.writeln('\nRecomendación: $accion');
      if (razon.isNotEmpty) sb.writeln('\n$razon');
      if (fechaVisible.isNotEmpty) sb.writeln('\nFecha visible en etiqueta: $fechaVisible');
      ref.read(_scanResultProvider.notifier).state = sb.toString().trim();
    } catch (e) {
      ref.read(_scanResultProvider.notifier).state = friendlyError(e);
    } finally {
      ref.read(_scanLoadingProvider.notifier).state = false;
    }
  }

  void _showPhotoOptions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey.shade900,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text(
                'Analizar producto con IA visual',
                style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
              ),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Text(
                'Kuine detecta frescura, daños y fecha de caducidad visible en la etiqueta',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.white54, fontSize: 12),
              ),
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt, color: Colors.white),
              title: const Text('Hacer foto ahora', style: TextStyle(color: Colors.white)),
              onTap: () {
                Navigator.pop(context);
                _analyzePhoto(source: ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined, color: Colors.white),
              title: const Text('Elegir de galería', style: TextStyle(color: Colors.white)),
              onTap: () {
                Navigator.pop(context);
                _analyzePhoto(source: ImageSource.gallery);
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final result = ref.watch(_scanResultProvider);
    final loading = ref.watch(_scanLoadingProvider);
    final lastBarcode = ref.watch(_lastBarcodeProvider);
    final cameraError = ref.watch(_cameraErrorProvider);
    final scanData = ref.watch(_scanDataProvider);

    if (kIsWeb) {
      return Scaffold(
        appBar: AppBar(title: const Text('Escanear producto')),
        body: _WebBarcodeEntry(
          onAnalyze: _analyzeBarcode,
          result: result,
          loading: loading,
          onReset: () {
            ref.read(_scanResultProvider.notifier).state = null;
            ref.read(_lastBarcodeProvider.notifier).state = null;
          },
        ),
      );
    }

    final batchMode = ref.watch(_batchModeProvider);
    final batchResults = ref.watch(_batchResultsProvider);

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: batchMode
            ? Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.layers_rounded, size: 18),
                const SizedBox(width: 6),
                Text('Modo batch (${batchResults.length} escaneados)'),
              ])
            : const Text('Escanear producto'),
        actions: [
          // Toggle batch mode
          Tooltip(
            message: batchMode ? 'Salir del modo batch' : 'Modo batch (varios productos)',
            child: IconButton(
              icon: Icon(batchMode ? Icons.layers_clear_rounded : Icons.layers_rounded),
              onPressed: () {
                final newBatch = !batchMode;
                ref.read(_batchModeProvider.notifier).state = newBatch;
                if (!newBatch) {
                  ref.read(_batchResultsProvider.notifier).state = [];
                  _resetScan();
                }
              },
            ),
          ),
          if (_cameraActive && cameraError == null)
            IconButton(
              icon: Icon(_torchOn ? Icons.flash_on : Icons.flash_off),
              onPressed: _toggleTorch,
              tooltip: _torchOn ? 'Apagar linterna' : 'Encender linterna',
            ),
          if (!batchMode)
            IconButton(
              icon: const Icon(Icons.photo_camera_outlined),
              tooltip: 'Analizar foto con IA',
              onPressed: loading ? null : () => _showPhotoOptions(context),
            ),
          if (!batchMode && (result != null || !_cameraActive || cameraError != null))
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: cameraError != null ? _retryCamera : _resetScan,
              tooltip: 'Nuevo escaneo',
            ),
        ],
      ),
      body: batchMode
          ? _BatchScanBody(
              cameraActive: _cameraActive,
              cameraError: cameraError,
              loading: loading,
              batchResults: batchResults,
              controller: _controller,
              onDetect: (capture) async {
                final barcode = capture.barcodes.firstOrNull?.rawValue;
                if (barcode == null || loading) return;
                // Evitar duplicados en el batch
                final already = batchResults.any((r) => r['barcode'] == barcode);
                if (already) return;
                ref.read(_scanLoadingProvider.notifier).state = true;
                try {
                  final response = await api.scan(barcode);
                  final newResults = [...batchResults, {...response, 'barcode': barcode}];
                  ref.read(_batchResultsProvider.notifier).state = newResults;
                } catch (_) {
                  final newResults = [...batchResults, {'barcode': barcode, 'error': true, 'result': 'Error analizando $barcode'}];
                  ref.read(_batchResultsProvider.notifier).state = newResults;
                } finally {
                  ref.read(_scanLoadingProvider.notifier).state = false;
                }
              },
              onError: _onCameraError,
              onRetry: _retryCamera,
              onClearAll: () {
                ref.read(_batchResultsProvider.notifier).state = [];
              },
            )
          : Column(
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
                                  ? _ScanResult(result: result, scanData: scanData, onScanAgain: _resetScan)
                                  : const SizedBox.shrink(),
                    ),
                  ),
              ],
            ),
    );
  }
}

// ── Batch scan body ───────────────────────────────────────────────────────────

class _BatchScanBody extends StatelessWidget {
  final bool cameraActive;
  final String? cameraError;
  final bool loading;
  final List<Map<String, dynamic>> batchResults;
  final MobileScannerController? controller;
  final Function(BarcodeCapture) onDetect;
  final Function(MobileScannerException) onError;
  final VoidCallback onRetry;
  final VoidCallback onClearAll;

  const _BatchScanBody({
    required this.cameraActive,
    required this.cameraError,
    required this.loading,
    required this.batchResults,
    required this.controller,
    required this.onDetect,
    required this.onError,
    required this.onRetry,
    required this.onClearAll,
  });

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // Cámara compacta — siempre visible en batch mode
      SizedBox(
        height: 200,
        child: _CameraViewport(
          cameraActive: cameraActive,
          cameraError: cameraError,
          lastBarcode: null,
          controller: controller,
          onDetect: onDetect,
          onError: onError,
          onRetry: onRetry,
        ),
      ),

      // Loading indicator batch
      if (loading)
        Container(
          color: const Color(0xFF059669),
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            SizedBox(width: 14, height: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)),
            SizedBox(width: 8),
            Text('Analizando...', style: TextStyle(color: Colors.white, fontSize: 12)),
          ]),
        ),

      // Lista de resultados batch
      Expanded(
        child: batchResults.isEmpty
            ? const Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.layers_rounded, size: 48, color: Color(0xFFD1D5DB)),
                  SizedBox(height: 12),
                  Text('Escanea productos uno a uno',
                      style: TextStyle(color: Color(0xFF6B7280), fontSize: 14)),
                  SizedBox(height: 4),
                  Text('Se acumulan aquí automáticamente',
                      style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
                ]),
              )
            : Column(children: [
                // Header con resumen y botón limpiar
                Container(
                  color: Colors.white,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: Row(children: [
                    Text('${batchResults.length} productos escaneados',
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600,
                            color: Color(0xFF111827))),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: onClearAll,
                      icon: const Icon(Icons.clear_all, size: 16),
                      label: const Text('Limpiar', style: TextStyle(fontSize: 12)),
                      style: TextButton.styleFrom(foregroundColor: const Color(0xFFEF4444)),
                    ),
                  ]),
                ),
                // Lista scrollable
                Expanded(
                  child: ListView.separated(
                    padding: const EdgeInsets.all(0),
                    itemCount: batchResults.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, i) {
                      final item = batchResults[batchResults.length - 1 - i]; // más reciente primero
                      final barcode = item['barcode'] as String? ?? '';
                      final hasError = item['error'] == true;
                      final productName = item['product_name'] as String? ?? barcode;
                      final daysLeft = item['days_left'] as int?;
                      final actionType = item['final_action'] as String? ?? item['action_type'] as String?;
                      final score = item['priority_score'] as int? ?? 0;

                      Color urgencyColor = const Color(0xFF059669);
                      if (hasError) {
                        urgencyColor = const Color(0xFF9CA3AF);
                      } else if (score >= 85) {
                        urgencyColor = const Color(0xFFEF4444);
                      } else if (score >= 65) {
                        urgencyColor = const Color(0xFFF59E0B);
                      }

                      final actionIcon = {
                        'rebajar': '💰', 'donar': '❤️', 'retirar': '🗑',
                        'revisar': '🔍', 'mover': '📦',
                      }[actionType] ?? '⚡';

                      return ListTile(
                        dense: true,
                        leading: Container(
                          width: 36, height: 36,
                          decoration: BoxDecoration(
                            color: urgencyColor.withValues(alpha: 0.1),
                            shape: BoxShape.circle,
                          ),
                          child: Center(child: Text(hasError ? '❌' : actionIcon,
                              style: const TextStyle(fontSize: 16))),
                        ),
                        title: Text(productName,
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                            maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: hasError
                            ? const Text('Error al analizar', style: TextStyle(fontSize: 11, color: Color(0xFFEF4444)))
                            : Text(
                                [
                                  if (actionType != null) actionType.toUpperCase(),
                                  if (daysLeft != null) '$daysLeft días',
                                  if (score > 0) 'score $score',
                                ].join(' · '),
                                style: TextStyle(fontSize: 11, color: urgencyColor),
                              ),
                        trailing: Text(barcode,
                            style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
                      );
                    },
                  ),
                ),
              ]),
      ),
    ]);
  }
}

// ── Web manual barcode entry ──────────────────────────────────────────────────

class _WebBarcodeEntry extends StatefulWidget {
  final Future<void> Function(String) onAnalyze;
  final String? result;
  final bool loading;
  final VoidCallback onReset;

  const _WebBarcodeEntry({
    required this.onAnalyze,
    required this.result,
    required this.loading,
    required this.onReset,
  });

  @override
  State<_WebBarcodeEntry> createState() => _WebBarcodeEntryState();
}

class _WebBarcodeEntryState extends State<_WebBarcodeEntry> {
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _submit() {
    final barcode = _ctrl.text.trim();
    if (barcode.isEmpty) return;
    widget.onAnalyze(barcode);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Info banner
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFF0FDF4),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF6EE7B7)),
            ),
            child: const Row(
              children: [
                Icon(Icons.info_outline, color: Color(0xFF059669), size: 20),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Demo web: introduce el código de barras manualmente. '
                    'La cámara está disponible en la app móvil.',
                    style: TextStyle(fontSize: 13, color: Color(0xFF065F46)),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // Barcode input
          TextField(
            controller: _ctrl,
            keyboardType: TextInputType.number,
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              labelText: 'Código de barras EAN',
              hintText: 'Ej: 8410001000001',
              prefixIcon: const Icon(Icons.qr_code),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              suffixIcon: IconButton(
                icon: const Icon(Icons.clear, size: 18),
                onPressed: () {
                  _ctrl.clear();
                  widget.onReset();
                },
              ),
            ),
          ),
          const SizedBox(height: 16),

          SizedBox(
            height: 50,
            child: ElevatedButton.icon(
              onPressed: widget.loading ? null : _submit,
              icon: widget.loading
                  ? const SizedBox(
                      width: 18, height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.search, size: 20),
              label: Text(widget.loading ? 'Analizando con Chuwi...' : 'Analizar producto'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF059669),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ),

          if (widget.result != null) ...[
            const SizedBox(height: 24),
            Expanded(
              child: _ScanResult(
                result: widget.result!,
                onScanAgain: () {
                  _ctrl.clear();
                  widget.onReset();
                },
              ),
            ),
          ],
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
              final msg = error.errorCode.name == 'permissionDenied'
                  ? 'Permiso de cámara denegado.\nVe a Ajustes → MermaOps → Cámara y actívalo.'
                  : error.errorCode.name == 'unsupported'
                      ? 'Tu dispositivo no soporta el escáner de cámara.'
                      : 'No se pudo inicializar la cámara.\nReinicia la aplicación e inténtalo de nuevo.';
              return Container(
                color: Colors.black87,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.no_photography_outlined,
                            color: Colors.white60, size: 56),
                        const SizedBox(height: 16),
                        Text(
                          msg,
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.5),
                        ),
                        const SizedBox(height: 24),
                        ElevatedButton.icon(
                          onPressed: onRetry,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Reintentar'),
                        ),
                      ],
                    ),
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

// ── Loading view — tres fases ─────────────────────────────────────────────────
// Fase 1 (0-1s):   "Leyendo código..." — shimmer en el área de resultado
// Fase 2 (1-3s):   "Consultando base de datos..." — indicador de progreso
// Fase 3 (3s+):    "Kuine analizando con IA..." — thinking animation

class _LoadingView extends StatefulWidget {
  const _LoadingView();

  @override
  State<_LoadingView> createState() => _LoadingViewState();
}

class _LoadingViewState extends State<_LoadingView>
    with TickerProviderStateMixin {
  int _phase = 0;
  late AnimationController _shimmerCtrl;
  late AnimationController _pulseCtrl;
  late Animation<double> _shimmerAnim;
  late Animation<double> _pulseAnim;

  static const _phases = [
    (Icons.qr_code_scanner_rounded, 'Leyendo código de barras...', Color(0xFF0891B2)),
    (Icons.storage_rounded, 'Consultando base de datos...', Color(0xFF7C3AED)),
    (Icons.psychology_rounded, 'Kuine analizando con IA...', Color(0xFF059669)),
  ];

  @override
  void initState() {
    super.initState();
    _shimmerCtrl = AnimationController(
      duration: const Duration(milliseconds: 1200), vsync: this)..repeat();
    _pulseCtrl = AnimationController(
      duration: const Duration(milliseconds: 800), vsync: this)..repeat(reverse: true);
    _shimmerAnim = Tween<double>(begin: -1.0, end: 2.0).animate(
        CurvedAnimation(parent: _shimmerCtrl, curve: Curves.easeInOut));
    _pulseAnim = Tween<double>(begin: 0.6, end: 1.0).animate(
        CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));

    // Avanzar fases automáticamente
    Future.delayed(const Duration(milliseconds: 900), () {
      if (mounted) setState(() => _phase = 1);
    });
    Future.delayed(const Duration(milliseconds: 2800), () {
      if (mounted) setState(() => _phase = 2);
    });
  }

  @override
  void dispose() {
    _shimmerCtrl.dispose();
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final (icon, label, color) = _phases[_phase];
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Icono animado de la fase
          AnimatedBuilder(
            animation: _pulseAnim,
            builder: (_, __) => Transform.scale(
              scale: _pulseAnim.value,
              child: Container(
                width: 64, height: 64,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                  border: Border.all(color: color.withValues(alpha: 0.3), width: 2),
                ),
                child: Icon(icon, color: color, size: 28),
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Texto de fase con transición
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Text(
              label,
              key: ValueKey(_phase),
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w600, color: Color(0xFF111827)),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: 8),

          // Indicador de progreso de fases
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(3, (i) => AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              margin: const EdgeInsets.symmetric(horizontal: 3),
              width: i == _phase ? 20 : 6,
              height: 6,
              decoration: BoxDecoration(
                color: i <= _phase ? color : const Color(0xFFE5E7EB),
                borderRadius: BorderRadius.circular(3),
              ),
            )),
          ),
          const SizedBox(height: 20),

          // Skeleton shimmer del resultado (preview del área que se llenará)
          AnimatedBuilder(
            animation: _shimmerAnim,
            builder: (_, __) => ShaderMask(
              shaderCallback: (bounds) => LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                stops: [
                  (_shimmerAnim.value - 0.4).clamp(0.0, 1.0),
                  _shimmerAnim.value.clamp(0.0, 1.0),
                  (_shimmerAnim.value + 0.4).clamp(0.0, 1.0),
                ],
                colors: const [Color(0xFFF3F4F6), Color(0xFFE5E7EB), Color(0xFFF3F4F6)],
              ).createShader(bounds),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SkeletonBar(width: double.infinity, height: 14),
                  const SizedBox(height: 8),
                  _SkeletonBar(width: 240, height: 12),
                  const SizedBox(height: 8),
                  _SkeletonBar(width: 180, height: 12),
                  const SizedBox(height: 12),
                  _SkeletonBar(width: double.infinity, height: 40),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SkeletonBar extends StatelessWidget {
  final double width;
  final double height;
  const _SkeletonBar({required this.width, required this.height});

  @override
  Widget build(BuildContext context) => Container(
    width: width, height: height,
    decoration: BoxDecoration(
      color: const Color(0xFFE5E7EB),
      borderRadius: BorderRadius.circular(4),
    ),
  );
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

class _ScanResult extends StatefulWidget {
  final String result;
  final Map<String, dynamic>? scanData;
  final VoidCallback onScanAgain;

  const _ScanResult({required this.result, this.scanData, required this.onScanAgain});

  @override
  State<_ScanResult> createState() => _ScanResultState();
}

class _ScanResultState extends State<_ScanResult> {
  bool _completing = false;
  bool _completed = false;

  String _actionLabel(String actionType) {
    switch (actionType.toLowerCase()) {
      case 'rebajar': return 'Confirmar rebaja';
      case 'donar': return 'Confirmar donación';
      case 'retirar': return 'Confirmar retirada';
      default: return 'Marcar como completada';
    }
  }

  Future<void> _completeAction(String actionId) async {
    setState(() => _completing = true);
    try {
      final userId = supabase.auth.currentUser?.id ?? 'app-user';
      await api.completeAction(
        actionId: actionId,
        completedBy: userId,
        notes: 'Completado desde escaneo en app',
      );
      setState(() { _completing = false; _completed = true; });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Acción marcada como completada'),
            backgroundColor: Color(0xFF059669),
            duration: Duration(seconds: 3),
          ),
        );
      }
    } catch (e) {
      setState(() => _completing = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error al completar: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    final scanData = widget.scanData;
    final actionId = scanData?['action_id'] as String?;
    final actionType = scanData?['action_type'] as String? ?? '';

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

    final actionLabel = _actionLabel(actionType);

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

        // Complete action button (only when there's a pending action)
        if (actionId != null && !_completed)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: SizedBox(
              width: double.infinity,
              height: 46,
              child: ElevatedButton.icon(
                icon: _completing
                    ? const SizedBox(
                        width: 16, height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.check_circle_outline, size: 18),
                label: Text(_completing ? 'Completando...' : actionLabel),
                onPressed: _completing ? null : () => _completeAction(actionId),
                style: ElevatedButton.styleFrom(
                  backgroundColor: hasCritical ? UrgencyColors.critical : const Color(0xFF059669),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ),

        if (_completed)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFD1FAE5),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFF6EE7B7)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.check_circle, color: Color(0xFF059669), size: 18),
                  SizedBox(width: 8),
                  Text('Acción completada', style: TextStyle(color: Color(0xFF065F46), fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),

        // Copy + scan again
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
                  onPressed: widget.onScanAgain,
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
