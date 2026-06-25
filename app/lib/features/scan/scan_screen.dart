import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/l10n.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';

final _scanResultProvider = StateProvider<String?>((ref) => null);
final _scanLoadingProvider = StateProvider<bool>((ref) => false);
final _lastBarcodeProvider = StateProvider<String?>((ref) => null);
final _cameraErrorProvider = StateProvider<String?>((ref) => null);
final _scanDataProvider = StateProvider<Map<String, dynamic>?>((ref) => null);

// ── Batch scan mode ───────────────────────────────────────────────────────────
final _batchModeProvider = StateProvider<bool>((ref) => false);
final _batchResultsProvider = StateProvider<List<Map<String, dynamic>>>((ref) => []);

// ── Historial de escaneos (persiste en SharedPreferences / localStorage web) ──
const _historyKey = 'scan_history_v1';
const _historyMax = 20;

class _HistoryNotifier extends StateNotifier<List<Map<String, dynamic>>> {
  _HistoryNotifier() : super([]) { _load(); }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getStringList(_historyKey) ?? [];
      state = raw.map((s) => Map<String, dynamic>.from(jsonDecode(s) as Map)).toList();
    } catch (_) {}
  }

  Future<void> add(Map<String, dynamic> entry) async {
    final updated = [entry, ...state].take(_historyMax).toList();
    state = updated;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList(_historyKey, updated.map(jsonEncode).toList());
    } catch (_) {}
  }

  Future<void> clear() async {
    state = [];
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_historyKey);
    } catch (_) {}
  }
}

final scanHistoryProvider = StateNotifierProvider<_HistoryNotifier, List<Map<String, dynamic>>>(
  (_) => _HistoryNotifier(),
);

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

      // Guardar en historial
      ref.read(scanHistoryProvider.notifier).add({
        'type': 'barcode',
        'barcode': barcode,
        'product_name': response['product_name'] ?? barcode,
        'action_type': response['final_action'] ?? response['action_type'] ?? '',
        'priority_score': response['priority_score'] ?? 0,
        'price_rec': response['price_rec'] ?? '',
        'ts': DateTime.now().toIso8601String(),
      });

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
        message = kIsWeb
            ? 'Permiso de cámara denegado por el navegador.\n\nHaz clic en el icono 🔒 de la barra de Chrome → Cámara → Permitir, y recarga.'
            : 'Permiso de cámara denegado.\n\nVe a Ajustes → MermaOps → Permisos → Cámara y actívala.';
        break;
      case MobileScannerErrorCode.unsupported:
        message = kIsWeb
            ? 'Tu navegador no soporta el escáner en tiempo real.\n\nUsa Chrome 83+ o Edge. En Firefox/Safari usa el campo de código manual de abajo.'
            : 'Este dispositivo no tiene cámara compatible.';
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
      final result = response['result'] as String? ?? 'Sin respuesta del servidor.';
      ref.read(_scanResultProvider.notifier).state = result;
      ref.read(_scanDataProvider.notifier).state = response;
      ref.read(scanHistoryProvider.notifier).add({
        'type': 'barcode',
        'barcode': barcode,
        'product_name': response['product_name'] ?? barcode,
        'action_type': response['final_action'] ?? response['action_type'] ?? '',
        'priority_score': response['priority_score'] ?? 0,
        'price_rec': response['price_rec'] ?? '',
        'ts': DateTime.now().toIso8601String(),
      });
    } catch (e) {
      ref.read(_scanResultProvider.notifier).state = friendlyError(e);
    } finally {
      ref.read(_scanLoadingProvider.notifier).state = false;
    }
  }

  Future<void> _analyzeShelf() async {
    if (ref.read(_scanLoadingProvider)) return;
    final picker = ImagePicker();
    final picked = await picker.pickImage(
      source: kIsWeb ? ImageSource.gallery : ImageSource.camera,
      maxWidth: 1600,
      imageQuality: 85,
    );
    if (picked == null) return;

    ref.read(_scanLoadingProvider.notifier).state = true;
    ref.read(_scanResultProvider.notifier).state = null;
    ref.read(_lastBarcodeProvider.notifier).state = '🗂️ Pasillo';
    _controller?.stop();
    setState(() => _cameraActive = false);

    try {
      final bytes = await picked.readAsBytes();
      final base64Image = base64Encode(bytes);
      final result = await api.analyzeShelf(imageBase64: base64Image);
      final productos = result['productos'] as List? ?? [];
      final total = result['total'] as int? ?? productos.length;
      final urgentes = result['urgentes'] as int? ?? 0;
      final sb = StringBuffer();
      sb.writeln('Análisis de pasillo — $total productos detectados, $urgentes urgentes\n');
      for (final p in productos) {
        final nombre = p['nombre'] as String? ?? 'Producto';
        final accion = (p['accion'] as String? ?? 'revisar').toUpperCase();
        final urgencia = p['urgencia'] as String? ?? '';
        final estado = p['estado'] as String? ?? '';
        final mark = urgencia == 'inmediata' ? '🔴' : urgencia == 'hoy' ? '🟡' : '🟢';
        sb.writeln('$mark $nombre → $accion ($estado)');
      }
      ref.read(_scanResultProvider.notifier).state = sb.toString().trim();
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

      ref.read(scanHistoryProvider.notifier).add({
        'type': 'photo',
        'barcode': '📷',
        'product_name': 'Foto — $estado',
        'action_type': accion,
        'priority_score': confianza ?? 0,
        'ts': DateTime.now().toIso8601String(),
      });
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

    // En web: pantalla de opciones siempre, la cámara abre en diálogo al pulsar el botón
    if (kIsWeb) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Escanear producto'),
          actions: [
            TextButton(
              onPressed: () => ref.read(languageProvider.notifier).toggle(),
              child: Text(ref.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
            ),
          ],
        ),
        body: _WebBarcodeEntry(
          onAnalyze: _analyzeBarcode,
          onAnalyzePhoto: () => _analyzePhoto(source: ImageSource.gallery),
          onAnalyzePhotoGallery: () => _analyzePhoto(source: ImageSource.gallery),
          onAnalyzeShelf: _analyzeShelf,
          result: result,
          loading: loading,
          onReset: () {
            ref.read(_scanResultProvider.notifier).state = null;
            ref.read(_lastBarcodeProvider.notifier).state = null;
          },
          onOpenCameraScanner: () async {
            final barcode = await showDialog<String>(
              context: context,
              barrierDismissible: false,
              builder: (_) => const _CameraScanDialog(),
            );
            if (barcode != null && barcode.isNotEmpty) {
              await _analyzeBarcode(barcode);
            }
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
          if (!batchMode)
            IconButton(
              icon: const Icon(Icons.view_list_outlined),
              tooltip: 'Analizar pasillo completo',
              onPressed: loading ? null : _analyzeShelf,
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
                        urgencyColor = const Color(0xFFD97706);
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

// ── Diálogo cámara en directo (web + móvil) ──────────────────────────────────

class _CameraScanDialog extends StatefulWidget {
  const _CameraScanDialog();
  @override
  State<_CameraScanDialog> createState() => _CameraScanDialogState();
}

class _CameraScanDialogState extends State<_CameraScanDialog> {
  late final MobileScannerController _ctrl;
  bool _detected = false;

  @override
  void initState() {
    super.initState();
    _ctrl = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      facing: kIsWeb ? CameraFacing.front : CameraFacing.back,
      torchEnabled: false,
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_detected) return;
    final code = capture.barcodes.firstOrNull?.rawValue;
    if (code != null && code.isNotEmpty) {
      _detected = true;
      HapticFeedback.mediumImpact();
      Navigator.of(context).pop(code);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog.fullscreen(
      backgroundColor: Colors.black,
      child: Stack(children: [
        // Visor de cámara
        MobileScanner(
          controller: _ctrl,
          onDetect: _onDetect,
          errorBuilder: (ctx, error, child) => Container(
            color: Colors.black,
            child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.no_photography_outlined, size: 64, color: Colors.white54),
              const SizedBox(height: 16),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Text(
                  error.errorCode == MobileScannerErrorCode.permissionDenied
                      ? 'Permiso de cámara denegado.\n\nEn Chrome: haz clic en el icono 🔒 en la barra de dirección → Cámara → Permitir → recarga.'
                      : 'Este navegador no soporta el escáner.\n\nUsa Chrome 83+ o Edge. Firefox y Safari no son compatibles.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, fontSize: 13, height: 1.6),
                ),
              ),
              const SizedBox(height: 24),
              OutlinedButton.icon(
                onPressed: () => Navigator.of(context).pop(null),
                icon: const Icon(Icons.arrow_back, color: Colors.white),
                label: const Text('Volver', style: TextStyle(color: Colors.white)),
                style: OutlinedButton.styleFrom(side: const BorderSide(color: Colors.white54)),
              ),
            ])),
          ),
        ),
        // Botón volver (arriba izquierda)
        Positioned(
          top: 0, left: 0,
          child: SafeArea(
            child: IconButton(
              icon: const Icon(Icons.arrow_back_rounded, color: Colors.white, size: 28),
              tooltip: 'Volver',
              onPressed: () => Navigator.of(context).pop(null),
              style: IconButton.styleFrom(
                backgroundColor: Colors.black45,
                padding: const EdgeInsets.all(10),
              ),
            ),
          ),
        ),
        // Marco de escaneo centrado
        Positioned.fill(child: IgnorePointer(child: CustomPaint(painter: _ScanFramePainter()))),
        // Etiqueta inferior
        Positioned(
          bottom: 48, left: 0, right: 0,
          child: const SafeArea(
            child: Column(children: [
              Icon(Icons.qr_code_2_rounded, color: Colors.white70, size: 32),
              SizedBox(height: 8),
              Text(
                'Apunta al código de barras o QR\nSe detecta automáticamente',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  height: 1.5,
                  shadows: [Shadow(color: Colors.black, blurRadius: 8)],
                ),
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _ScanFramePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final half = size.width * 0.35;
    final rect = Rect.fromCenter(center: Offset(cx, cy), width: half * 2, height: half * 2);

    // Oscurece todo menos el cuadro
    canvas.drawPath(
      Path.combine(PathOperation.difference,
        Path()..addRect(Offset.zero & size),
        Path()..addRRect(RRect.fromRectAndRadius(rect, const Radius.circular(12))),
      ),
      Paint()..color = Colors.black54,
    );

    // Esquinas del marco
    final corner = Paint()
      ..color = const Color(0xFF34D399)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const len = 24.0;
    final l = rect.left; final t = rect.top; final r = rect.right; final b = rect.bottom;
    for (final pts in [
      [Offset(l, t + len), Offset(l, t), Offset(l + len, t)],
      [Offset(r - len, t), Offset(r, t), Offset(r, t + len)],
      [Offset(r, b - len), Offset(r, b), Offset(r - len, b)],
      [Offset(l + len, b), Offset(l, b), Offset(l, b - len)],
    ]) {
      final path = Path()..moveTo(pts[0].dx, pts[0].dy)..lineTo(pts[1].dx, pts[1].dy)..lineTo(pts[2].dx, pts[2].dy);
      canvas.drawPath(path, corner);
    }
  }

  @override
  bool shouldRepaint(_) => false;
}

// ── Web manual barcode entry ──────────────────────────────────────────────────

class _WebBarcodeEntry extends StatefulWidget {
  final Future<void> Function(String) onAnalyze;
  final Future<void> Function()? onAnalyzePhoto;
  final Future<void> Function()? onAnalyzePhotoGallery;
  final Future<void> Function()? onAnalyzeShelf;
  final Future<void> Function()? onOpenCameraScanner;
  final String? result;
  final bool loading;
  final VoidCallback onReset;

  const _WebBarcodeEntry({
    required this.onAnalyze,
    this.onAnalyzePhoto,
    this.onAnalyzePhotoGallery,
    this.onAnalyzeShelf,
    this.onOpenCameraScanner,
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
    final isLoading = widget.loading;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Botón principal: escáner de código de barras con cámara en directo
          _ScanActionCard(
            icon: Icons.qr_code_scanner_rounded,
            title: 'Escanear código de barras',
            subtitle: 'Abre la cámara y lee el código automáticamente',
            color: const Color(0xFF059669),
            loading: isLoading,
            onTap: widget.onOpenCameraScanner,
          ),
          const SizedBox(height: 12),
          // Analizar foto con IA
          _ScanActionCard(
            icon: Icons.camera_alt_rounded,
            title: 'Analizar foto con IA',
            subtitle: 'Detecta frescura, daños y fecha de caducidad',
            color: const Color(0xFF7C3AED),
            loading: isLoading,
            onTap: widget.onAnalyzePhoto,
          ),
          const SizedBox(height: 12),

          // Secondary: gallery
          _ScanActionCard(
            icon: Icons.photo_library_outlined,
            title: 'Analizar foto de galería',
            subtitle: 'Selecciona una imagen ya tomada',
            color: const Color(0xFF0284C7),
            loading: isLoading,
            onTap: widget.onAnalyzePhotoGallery,
          ),
          const SizedBox(height: 12),

          // Shelf analysis
          if (widget.onAnalyzeShelf != null)
            _ScanActionCard(
              icon: Icons.view_list_outlined,
              title: 'Analizar pasillo completo',
              subtitle: 'Detecta múltiples productos en una sola foto',
              color: const Color(0xFF7C3AED),
              loading: isLoading,
              onTap: widget.onAnalyzeShelf,
            ),

          const SizedBox(height: 24),

          // Divider with label
          Row(children: [
            const Expanded(child: Divider()),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('o introduce código de barras',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade500)),
            ),
            const Expanded(child: Divider()),
          ]),

          const SizedBox(height: 16),

          // Barcode input row
          Row(children: [
            Expanded(
              child: TextField(
                controller: _ctrl,
                keyboardType: TextInputType.number,
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: 'EAN / código de barras',
                  hintText: '8410001000001',
                  prefixIcon: const Icon(Icons.qr_code),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                  contentPadding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.clear, size: 18),
                    onPressed: () { _ctrl.clear(); widget.onReset(); },
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              height: 54,
              child: ElevatedButton(
                onPressed: isLoading ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF059669),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                ),
                child: isLoading
                    ? const SizedBox(width: 18, height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.search, size: 22),
              ),
            ),
          ]),

          const SizedBox(height: 24),

          // Result or history
          if (widget.result != null)
            _ScanResult(
              result: widget.result!,
              onScanAgain: () { _ctrl.clear(); widget.onReset(); },
            )
          else ...[
            const SizedBox(height: 320, child: _ScanHistoryWidget()),
            const SizedBox(height: 24),
            // How it works guide
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF0FDF4),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFBBF7D0)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [
                  Icon(Icons.lightbulb_outline, size: 16, color: Color(0xFF059669)),
                  SizedBox(width: 8),
                  Text('Cómo funciona', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF065F46))),
                ]),
                const SizedBox(height: 12),
                _ScanGuideRow(step: '1', icon: Icons.qr_code_2, text: 'Introduce el código EAN o escanea con cámara'),
                _ScanGuideRow(step: '2', icon: Icons.psychology_rounded, text: 'Kuine consulta el inventario y evalúa la urgencia'),
                _ScanGuideRow(step: '3', icon: Icons.flag_outlined, text: 'Recibes la acción recomendada (rebajar, donar, retirar…)'),
                _ScanGuideRow(step: '4', icon: Icons.check_circle_outline, text: 'Ejecuta la acción y se registra en el informe diario'),
              ]),
            ),
            const SizedBox(height: 16),
            // Tips
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFFEF9C3),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFFDE68A)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Row(children: [
                  Icon(Icons.tips_and_updates_outlined, size: 16, color: Color(0xFFD97706)),
                  SizedBox(width: 8),
                  Text('Consejos de escaneo', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF92400E))),
                ]),
                const SizedBox(height: 10),
                ...[
                  '📷 Usa "Detectar con IA" para productos sin código visible',
                  '📋 El modo batch permite escanear varios productos seguidos',
                  '🔦 Activa la linterna en la cámara si hay poca luz',
                  '📊 Los escaneos se guardan en historial y se sincronizan con Telegram',
                ].map((tip) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(tip, style: const TextStyle(fontSize: 12, color: Color(0xFF78350F), height: 1.4)),
                )),
              ]),
            ),
            const SizedBox(height: 16),
            // Shortcut actions
            Row(children: [
              Expanded(
                child: _ShortcutCard(
                  icon: Icons.layers_rounded,
                  title: 'Modo batch',
                  subtitle: 'Varios productos',
                  color: const Color(0xFF7C3AED),
                  onTap: null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _ShortcutCard(
                  icon: Icons.view_list_outlined,
                  title: 'Pasillo completo',
                  subtitle: 'Una sola foto',
                  color: const Color(0xFF0284C7),
                  onTap: widget.onAnalyzeShelf,
                ),
              ),
            ]),
          ],
        ],
      ),
    );
  }
}

class _ScanGuideRow extends StatelessWidget {
  final String step;
  final IconData icon;
  final String text;
  const _ScanGuideRow({required this.step, required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        Container(
          width: 22, height: 22,
          decoration: BoxDecoration(
            color: const Color(0xFF059669),
            borderRadius: BorderRadius.circular(11),
          ),
          child: Center(child: Text(step, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800))),
        ),
        const SizedBox(width: 10),
        Icon(icon, size: 16, color: const Color(0xFF059669)),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 12, color: Color(0xFF065F46), height: 1.3))),
      ]),
    );
  }
}

class _ShortcutCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback? onTap;
  const _ShortcutCard({required this.icon, required this.title, required this.subtitle, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color.withValues(alpha: 0.08),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 6),
            Text(title, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: color)),
            Text(subtitle, style: TextStyle(fontSize: 11, color: color.withValues(alpha: 0.7))),
          ]),
        ),
      ),
    );
  }
}

class _ScanActionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final bool loading;
  final VoidCallback? onTap;

  const _ScanActionCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.loading,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color.withValues(alpha: 0.07),
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: loading ? null : onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(children: [
            Container(
              width: 48, height: 48,
              decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12)),
              child: loading
                  ? const Center(child: SizedBox(width: 22, height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)))
                  : Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w700, color: color)),
                const SizedBox(height: 2),
                Text(subtitle, style: TextStyle(
                    fontSize: 12, color: Colors.grey.shade600)),
              ],
            )),
            Icon(Icons.chevron_right, color: color.withValues(alpha: 0.5)),
          ]),
        ),
      ),
    );
  }
}

// ── Historial de escaneos ─────────────────────────────────────────────────────

class _ScanHistoryWidget extends ConsumerWidget {
  const _ScanHistoryWidget();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(scanHistoryProvider);
    if (history.isEmpty) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.history, size: 40, color: Color(0xFFD1D5DB)),
          SizedBox(height: 8),
          Text('Sin escaneos recientes',
              style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 13)),
        ]),
      );
    }
    return Column(children: [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: Row(children: [
          const Text('Últimos escaneos',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF6B7280))),
          const Spacer(),
          TextButton(
            style: TextButton.styleFrom(
                padding: EdgeInsets.zero, minimumSize: const Size(40, 24)),
            onPressed: () => ref.read(scanHistoryProvider.notifier).clear(),
            child: const Text('Limpiar',
                style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
          ),
        ]),
      ),
      Expanded(
        child: ListView.separated(
          padding: EdgeInsets.zero,
          itemCount: history.length,
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemBuilder: (_, i) {
            final item = history[i];
            final type = item['type'] as String? ?? 'barcode';
            final name = item['product_name'] as String? ?? '';
            final action = (item['action_type'] as String? ?? '').toUpperCase();
            final score = item['priority_score'] as int? ?? 0;
            final ts = item['ts'] as String? ?? '';
            final time = ts.isNotEmpty ? ts.substring(11, 16) : '';
            final priceRec = item['price_rec'] as String? ?? '';

            Color scoreColor = const Color(0xFF059669);
            if (score >= 85) {
              scoreColor = const Color(0xFFDC2626);
            } else if (score >= 65) {
              scoreColor = const Color(0xFFD97706);
            }

            return ListTile(
              dense: true,
              leading: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  color: scoreColor.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                child: Center(child: Text(
                  type == 'photo' ? '📷' : '📦',
                  style: const TextStyle(fontSize: 14),
                )),
              ),
              title: Text(name,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
              subtitle: action.isNotEmpty
                  ? Text(
                      priceRec.isNotEmpty ? '$action · $priceRec' : action,
                      style: TextStyle(fontSize: 11, color: scoreColor))
                  : (priceRec.isNotEmpty
                      ? Text(priceRec, style: const TextStyle(fontSize: 11, color: Color(0xFF059669)))
                      : null),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(time, style: const TextStyle(fontSize: 10, color: Color(0xFF9CA3AF))),
                const SizedBox(width: 4),
                const Icon(Icons.chevron_right, size: 14, color: Color(0xFFD1D5DB)),
              ]),
              onTap: () => _showScanHistoryDetail(context, item),
            );
          },
        ),
      ),
    ]);
  }
}

void _showScanHistoryDetail(BuildContext context, Map<String, dynamic> item) {
  final type = item['type'] as String? ?? 'barcode';
  final name = item['product_name'] as String? ?? '';
  final barcode = item['barcode'] as String? ?? '';
  final action = item['action_type'] as String? ?? '';
  final score = item['priority_score'] as int? ?? 0;
  final ts = item['ts'] as String? ?? '';
  final priceRec = item['price_rec'] as String? ?? '';

  Color scoreColor;
  String scoreLabel;
  if (score >= 85) {
    scoreColor = const Color(0xFFDC2626);
    scoreLabel = 'CRÍTICO';
  } else if (score >= 65) {
    scoreColor = const Color(0xFFD97706);
    scoreLabel = 'URGENTE';
  } else if (score > 0) {
    scoreColor = const Color(0xFF059669);
    scoreLabel = 'NORMAL';
  } else {
    scoreColor = const Color(0xFF9CA3AF);
    scoreLabel = '';
  }

  String dateStr = '';
  String timeStr = '';
  if (ts.isNotEmpty) {
    try {
      final dt = DateTime.parse(ts).toLocal();
      const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
      dateStr = '${dt.day} ${months[dt.month - 1]} ${dt.year}';
      timeStr = '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {}
  }

  showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) => Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 36, height: 4,
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(2)),
            ),
          ),
          Row(children: [
            Container(
              width: 52, height: 52,
              decoration: BoxDecoration(
                color: scoreColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Center(child: Text(
                type == 'photo' ? '📷' : '📦',
                style: const TextStyle(fontSize: 26),
              )),
            ),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                name.isNotEmpty ? name : 'Sin nombre',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: Color(0xFF111827)),
              ),
              const SizedBox(height: 2),
              Text(
                type == 'photo' ? 'Análisis de fotografía' : 'Escaneo de código de barras',
                style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
              ),
            ])),
          ]),
          const SizedBox(height: 16),
          const Divider(),
          const SizedBox(height: 8),
          if (barcode.isNotEmpty && barcode != '📷') ...[
            _ScanDetailRow(icon: Icons.qr_code_outlined, label: 'Código', value: barcode),
            const SizedBox(height: 10),
          ],
          if (action.isNotEmpty) ...[
            _ScanDetailRow(icon: Icons.flag_outlined, label: 'Acción recomendada', value: action),
            const SizedBox(height: 10),
          ],
          if (priceRec.isNotEmpty) ...[
            _ScanDetailRow(icon: Icons.sell_outlined, label: 'Precio recomendado', value: priceRec),
            const SizedBox(height: 10),
          ],
          if (score > 0) ...[
            Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
              const Icon(Icons.speed_outlined, size: 16, color: Color(0xFF6B7280)),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Prioridad', style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
                const SizedBox(height: 4),
                Row(children: [
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: score / 100,
                        backgroundColor: Colors.grey[200],
                        valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
                        minHeight: 8,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('$score', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: scoreColor)),
                  if (scoreLabel.isNotEmpty) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: scoreColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(scoreLabel, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: scoreColor)),
                    ),
                  ],
                ]),
              ])),
            ]),
            const SizedBox(height: 10),
          ],
          if (dateStr.isNotEmpty)
            _ScanDetailRow(icon: Icons.calendar_today_outlined, label: 'Fecha y hora', value: '$dateStr · $timeStr'),
        ],
      ),
    ),
  );
}

class _ScanDetailRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  const _ScanDetailRow({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Icon(icon, size: 16, color: const Color(0xFF6B7280)),
      const SizedBox(width: 10),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF111827))),
      ])),
    ]);
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
