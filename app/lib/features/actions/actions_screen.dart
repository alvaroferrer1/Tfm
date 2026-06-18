import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_service.dart';
import '../../core/file_download.dart';
import '../../core/l10n.dart';
import '../../core/error_widget.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart' show UrgencyColors, ShimmerList;
import '../../core/user_role_provider.dart';
import 'actions_provider.dart';

const _pasilloNames = {
  '1': 'Panadería', '2': 'Lácteos', '3': 'Carnicería',
  '4': 'Pescadería', '5': 'Frutas/Verduras',
};
String _pasilloLabel(String? n) {
  if (n == null || n == '?' || n.isEmpty) return 'Sin ubicación';
  return _pasilloNames[n] ?? 'Pasillo $n';
}

// Propuestas de staff pendientes de aprobación (status = in_progress)
final _proposalsProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  try {
    return await ApiService().getProposals();
  } catch (_) {
    return [];
  }
});

// Caché de productos vía backend (bypassa RLS de Supabase en tabla products)
final _actionProductsCacheProvider = FutureProvider<Map<String, Map<String, dynamic>>>((ref) async {
  try {
    final products = await api.getProducts();
    return {for (final p in products) p['id'] as String: p};
  } catch (_) {
    return {};
  }
});

Map<String, dynamic> _enrichAction(
    Map<String, dynamic> action, Map<String, Map<String, dynamic>> cache) {
  final batch = action['batches'] as Map<String, dynamic>?;
  if (batch == null) return action;
  if (batch['products'] != null) return action;
  final pid = batch['product_id'] as String?;
  if (pid != null && cache.containsKey(pid)) {
    final enrichedBatch = Map<String, dynamic>.from(batch)..['products'] = cache[pid];
    return Map<String, dynamic>.from(action)..['batches'] = enrichedBatch;
  }
  return action;
}

class ActionsScreen extends ConsumerStatefulWidget {
  const ActionsScreen({super.key});

  @override
  ConsumerState<ActionsScreen> createState() => _ActionsScreenState();
}

class _ActionsScreenState extends ConsumerState<ActionsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // StreamProvider para actualizaciones en tiempo real via Supabase Realtime
    final actionsAsync = ref.watch(pendingActionsStreamProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Acciones'),
        actions: [
          TextButton(
            onPressed: () => ref.read(languageProvider.notifier).toggle(),
            child: Text(ref.watch(languageProvider) == 'es' ? 'EN' : 'ES',
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
          ),
          IconButton(
            icon: const Icon(Icons.download_outlined),
            tooltip: 'Exportar CSV',
            onPressed: () => _exportAndShare(context),
          ),
          IconButton(
            icon: const Icon(Icons.upload_file_outlined),
            tooltip: 'Importar CSV',
            onPressed: () => _showImportDialog(context),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Actualizar',
            onPressed: () {
              ref.invalidate(pendingActionsStreamProvider);
              ref.invalidate(pendingActionsProvider);
              ref.invalidate(completedActionsProvider);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Actualizando acciones…'),
                  duration: Duration(seconds: 1),
                ),
              );
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          tabs: [
            Tab(
              child: actionsAsync.when(
                data: (a) => Text('Pendientes (${a.length})'),
                loading: () => const Text('Pendientes'),
                error: (_, __) => const Text('Pendientes'),
              ),
            ),
            const Tab(text: 'Historial'),
          ],
        ),
      ),
      body: Column(
        children: [
          _DailyProgressHeader(actionsAsync: actionsAsync),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: [
                _PendingTab(
                  onComplete: _showCompleteDialog,
                  onDonate: _showDonateDialog,
                ),
                const _HistorialTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _exportAndShare(BuildContext context) async {
    final api = ApiService();
    try {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Generando parte diario PDF…'), duration: Duration(seconds: 2)),
      );
      final bytes = await api.downloadDailySheetPdf();
      final now = DateTime.now();
      final name = 'parte_diario_'
          '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}.pdf';

      if (kIsWeb) {
        downloadPdf(name, bytes);
      } else {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}/$name');
        await file.writeAsBytes(bytes);
        await Share.shareXFiles([XFile(file.path)], text: 'Parte diario — MermaOps');
      }

      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF descargado: $name'), backgroundColor: const Color(0xFF059669)),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se pudo exportar. Comprueba que el servidor está activo.'),
            backgroundColor: Color(0xFFDC2626),
          ),
        );
      }
    }
  }

  Future<void> _showImportDialog(BuildContext context) async {
    // Abrir explorador de archivos — múltiples CSV permitidos
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['csv', 'txt'],
      allowMultiple: true,
      withData: true,
    );
    if (picked == null || picked.files.isEmpty) return;
    if (!context.mounted) return;

    int totalImported = 0;
    int totalErrors = 0;
    final fileNames = <String>[];

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Importando ${picked.files.length} archivo(s)…'),
        duration: const Duration(seconds: 2),
      ),
    );

    for (final file in picked.files) {
      try {
        final bytes = file.bytes;
        if (bytes == null) continue;
        final content = utf8.decode(bytes);
        final res = await ApiService().importBatches(content);
        totalImported += (res['imported'] as int? ?? 0);
        totalErrors += (res['errors'] as int? ?? 0);
        fileNames.add(file.name);
      } catch (_) {
        totalErrors++;
      }
    }

    if (totalImported > 0) ref.invalidate(pendingActionsStreamProvider);

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '✓ ${fileNames.join(', ')} — $totalImported lotes importados'
            '${totalErrors > 0 ? ' · $totalErrors errores' : ''}',
          ),
          backgroundColor: totalErrors > 0 ? Colors.orange : const Color(0xFF059669),
          duration: const Duration(seconds: 4),
        ),
      );
    }
  }

  void _showCompleteDialog(
      BuildContext context, WidgetRef ref, Map<String, dynamic> action) {
    final actionType = action['action_type'] as String? ?? '';
    if (actionType == 'donar') {
      _showDonateDialog(context, ref, action);
      return;
    }

    final notesCtrl = TextEditingController();
    XFile? photoFile;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => StatefulBuilder(
        builder: (ctx, setModalState) => Padding(
          padding: EdgeInsets.fromLTRB(
            16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 16,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Marcar como completada',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: notesCtrl,
                decoration: const InputDecoration(
                  labelText: 'Notas (opcional)',
                  hintText: 'Ej: rebajado al precio indicado',
                ),
                maxLines: 2,
              ),
              const SizedBox(height: 12),
              // Photo evidence
              GestureDetector(
                onTap: () async {
                  final picker = ImagePicker();
                  final picked = await picker.pickImage(
                    source: ImageSource.camera,
                    maxWidth: 1200,
                    imageQuality: 85,
                  );
                  if (picked != null) setModalState(() => photoFile = picked);
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: photoFile != null
                        ? const Color(0xFFD1FAE5)
                        : const Color(0xFFF9FAFB),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: photoFile != null
                          ? const Color(0xFF059669)
                          : const Color(0xFFD1D5DB),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        photoFile != null
                            ? Icons.check_circle_outline
                            : Icons.camera_alt_outlined,
                        color: photoFile != null
                            ? const Color(0xFF059669)
                            : Colors.grey,
                        size: 20,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          photoFile != null
                              ? 'Foto adjuntada — toca para cambiar'
                              : 'Adjuntar foto como evidencia (opcional)',
                          style: TextStyle(
                            fontSize: 13,
                            color: photoFile != null
                                ? const Color(0xFF059669)
                                : Colors.grey[600],
                          ),
                        ),
                      ),
                      if (photoFile != null)
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: FutureBuilder<Uint8List>(
                            future: photoFile!.readAsBytes(),
                            builder: (_, snap) => snap.hasData
                                ? Image.memory(snap.data!,
                                    width: 40, height: 40, fit: BoxFit.cover)
                                : const SizedBox(width: 40, height: 40),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () async {
                  Navigator.pop(context);
                  await _completeAction(
                    ref,
                    action['id'] as String,
                    notesCtrl.text,
                    photoFile,
                  );
                },
                child: const Text('Confirmar acción completada'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showDonateDialog(
      BuildContext context, WidgetRef ref, Map<String, dynamic> action) {
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';
    final maxQty = batch?['quantity'] as int? ?? 1;
    final price = (product?['price'] as num?)?.toDouble() ?? 0.0;
    final actionType = action['action_type'] as String? ?? '';

    const entities = [
      'Banco de Alimentos de Madrid',
      'Cáritas',
      'Cruz Roja',
      'Comedor Social Municipal',
      'Otro',
    ];

    String selectedEntity = entities.first;
    final qtyCtrl = TextEditingController(text: '$maxQty');
    final notesCtrl = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => StatefulBuilder(
        builder: (ctx, setModalState) {
          final qty = int.tryParse(qtyCtrl.text) ?? maxQty;
          final totalValue = price * qty;
          // Ley 49/2002: deducción fiscal del 35% por donaciones a entidades sin ánimo de lucro
          final fiscalDeduction = totalValue * 0.35;

          return SingleChildScrollView(
            padding: EdgeInsets.fromLTRB(
              16, 20, 16, MediaQuery.of(ctx).viewInsets.bottom + 20,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFD1FAE5),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(Icons.volunteer_activism,
                          color: Color(0xFF059669), size: 22),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            actionType == 'rebajar'
                                ? 'Donar en lugar de rebajar'
                                : actionType == 'retirar'
                                    ? 'Donar en lugar de retirar'
                                    : 'Registrar donación',
                            style: const TextStyle(
                                fontSize: 17, fontWeight: FontWeight.w800),
                          ),
                          Text(
                            productName,
                            style: const TextStyle(
                                fontSize: 13, color: Colors.grey),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                // Beneficio fiscal highlight
                if (price > 0)
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0FDF4),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFF6EE7B7)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.savings_outlined,
                            color: Color(0xFF059669), size: 20),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Beneficio fiscal (Ley 49/2002)',
                                style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF059669)),
                              ),
                              Text(
                                'Deducción estimada: ${fiscalDeduction.toStringAsFixed(2)} € '
                                '(35% de ${totalValue.toStringAsFixed(2)} €)',
                                style: const TextStyle(
                                    fontSize: 11, color: Color(0xFF065F46)),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 14),

                // Cantidad
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: qtyCtrl,
                        keyboardType: TextInputType.number,
                        onChanged: (_) => setModalState(() {}),
                        decoration: InputDecoration(
                          labelText: 'Unidades (máx. $maxQty)',
                          suffixText: 'uds',
                          border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: notesCtrl,
                        decoration: InputDecoration(
                          labelText: 'Notas (opcional)',
                          border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                // Entidad
                const Text(
                  'Entidad receptora',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: entities.map((e) {
                    final selected = selectedEntity == e;
                    return GestureDetector(
                      onTap: () => setModalState(() => selectedEntity = e),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 7),
                        decoration: BoxDecoration(
                          color: selected
                              ? const Color(0xFF059669)
                              : const Color(0xFFF9FAFB),
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: selected
                                ? const Color(0xFF059669)
                                : const Color(0xFFD1D5DB),
                          ),
                        ),
                        child: Text(
                          e,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: selected ? Colors.white : Colors.grey[700],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 18),

                ElevatedButton.icon(
                  icon: const Icon(Icons.favorite, size: 18),
                  label: Text(
                      'Confirmar donación — $qty uds a $selectedEntity'),
                  onPressed: () async {
                    Navigator.pop(context);
                    await _completeDonation(
                      ref,
                      action,
                      entity: selectedEntity,
                      quantity: qty,
                      notes: notesCtrl.text,
                    );
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            '✓ Donados $qty uds de $productName a $selectedEntity'
                            '${fiscalDeduction > 0 ? ' · Deducción fiscal: ${fiscalDeduction.toStringAsFixed(2)} €' : ''}',
                          ),
                          backgroundColor: const Color(0xFF059669),
                          duration: const Duration(seconds: 5),
                        ),
                      );
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF059669),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _completeDonation(
    WidgetRef ref,
    Map<String, dynamic> action, {
    required String entity,
    required int quantity,
    String notes = '',
  }) async {
    final userLabel = supabase.auth.currentUser?.email ??
        supabase.auth.currentUser?.id ?? 'unknown';
    final actionId = action['id'] as String;
    // Siempre va al backend — tiene clave de servicio que bypasea RLS
    await api.completeAction(
      actionId: actionId,
      completedBy: userLabel,
      notes: 'Donado a $entity — $quantity uds${notes.isNotEmpty ? ' · $notes' : ''}',
    );
    ref.invalidate(pendingActionsStreamProvider);
    ref.invalidate(completedActionsProvider);
  }

  Future<void> _completeAction(
    WidgetRef ref,
    String actionId,
    String notes,
    XFile? photoFile,
  ) async {
    // Use email for completed_by so the historial shows a readable name, not a UUID
    final userId = supabase.auth.currentUser?.email ??
        supabase.auth.currentUser?.id ??
        'unknown';
    String photoUrl = '';

    if (photoFile != null) {
      try {
        final bytes = await photoFile.readAsBytes();
        final path =
            'actions/$actionId/${DateTime.now().millisecondsSinceEpoch}.jpg';
        await supabase.storage.from('evidence').uploadBinary(path, bytes);
        photoUrl = supabase.storage.from('evidence').getPublicUrl(path);
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Foto no guardada: ${e.toString().split(':').first}'),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 3),
          ));
        }
      }
    }

    bool synced = false;
    try {
      // Siempre al backend — bypasea RLS con clave de servicio
      await api.completeAction(
        actionId: actionId,
        completedBy: userId,
        notes: notes,
        photoUrl: photoUrl,
      );
      synced = true;
    } catch (e2) {
      // Red no disponible → guardar en cola offline
      await _OfflineQueue.enqueue(actionId, userId, notes, photoUrl);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Sin conexión — acción guardada (${e2.toString().split(':').first})'),
          backgroundColor: const Color(0xFFF59E0B),
          duration: const Duration(seconds: 4),
        ));
      }
    }
    if (synced) {
      ref.invalidate(pendingActionsStreamProvider);
      ref.invalidate(completedActionsProvider);
      // Intentar sincronizar pendientes anteriores también
      await _OfflineQueue.flush(ref);
    }

    // Celebración visual para acciones críticas
    if (mounted) {
      HapticFeedback.heavyImpact();
      _showCompletionCelebration(context);
    }
  }

  void _showCompletionCelebration(BuildContext context) {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;
    entry = OverlayEntry(builder: (_) => _CelebrationOverlay(onDone: () => entry.remove()));
    overlay.insert(entry);
  }
}

// ── Celebration overlay — aparece al completar una acción crítica ─────────────
// Animación de checkmark + partículas que desaparece sola en 1.5s.

// ── Offline action queue ──────────────────────────────────────────────────────
// Persiste acciones completadas en SharedPreferences cuando no hay red.
// Se sincronizan automáticamente cuando la conexión se restaura.

class _OfflineQueue {
  static const _key = 'offline_actions_queue';

  static Future<void> enqueue(
    String actionId, String userId, String notes, String photoUrl,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_key) ?? [];
    raw.add('$actionId|$userId|${Uri.encodeComponent(notes)}|$photoUrl');
    await prefs.setStringList(_key, raw);
  }

  static Future<void> flush(WidgetRef ref) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_key) ?? [];
    if (raw.isEmpty) return;

    final remaining = <String>[];
    for (final item in raw) {
      final parts = item.split('|');
      if (parts.length < 2) continue;
      final actionId = parts[0];
      final userId = parts[1];
      final notes = parts.length > 2 ? Uri.decodeComponent(parts[2]) : '';
      final photoUrl = parts.length > 3 ? parts[3] : '';
      try {
        await supabase.from('actions').update({
          'status': 'completed',
          'completed_by': userId,
          'completed_at': DateTime.now().toUtc().toIso8601String(),
          'notes': notes,
          if (photoUrl.isNotEmpty) 'photo_url': photoUrl,
        }).eq('id', actionId);
        ref.invalidate(pendingActionsStreamProvider);
        ref.invalidate(completedActionsProvider);
      } catch (_) {
        remaining.add(item); // mantener en cola si aún falla
      }
    }
    await prefs.setStringList(_key, remaining);
  }

}

class _CelebrationOverlay extends StatefulWidget {
  final VoidCallback onDone;
  const _CelebrationOverlay({required this.onDone});

  @override
  State<_CelebrationOverlay> createState() => _CelebrationOverlayState();
}

class _CelebrationOverlayState extends State<_CelebrationOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _scaleAnim;
  late Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _scaleAnim = TweenSequence([
      TweenSequenceItem(tween: Tween<double>(begin: 0.3, end: 1.2).chain(CurveTween(curve: Curves.elasticOut)), weight: 60),
      TweenSequenceItem(tween: Tween<double>(begin: 1.2, end: 1.0), weight: 20),
      TweenSequenceItem(tween: Tween<double>(begin: 1.0, end: 0.0), weight: 20),
    ]).animate(_ctrl);
    _fadeAnim = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(parent: _ctrl, curve: const Interval(0.7, 1.0)),
    );
    _ctrl.forward().whenComplete(widget.onDone);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) => Opacity(
        opacity: _fadeAnim.value,
        child: Center(
          child: Transform.scale(
            scale: _scaleAnim.value,
            child: Container(
              width: 120, height: 120,
              decoration: BoxDecoration(
                color: const Color(0xFF059669),
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(color: const Color(0xFF059669).withValues(alpha: 0.4), blurRadius: 30, spreadRadius: 10),
                ],
              ),
              child: const Icon(Icons.check_rounded, color: Colors.white, size: 60),
            ),
          ),
        ),
      ),
    );
  }
}

class _PendingTab extends ConsumerWidget {
  final void Function(BuildContext, WidgetRef, Map<String, dynamic>) onComplete;
  final void Function(BuildContext, WidgetRef, Map<String, dynamic>) onDonate;

  const _PendingTab({required this.onComplete, required this.onDonate});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final actionsAsync = ref.watch(pendingActionsStreamProvider);
    final productsCache = ref.watch(_actionProductsCacheProvider).valueOrNull ?? {};
    final role = ref.watch(userRoleProvider).valueOrNull ?? UserRole.staff;
    final isManager = role.index >= UserRole.manager.index;
    final proposals = isManager ? (ref.watch(_proposalsProvider).valueOrNull ?? []) : <Map<String, dynamic>>[];

    return actionsAsync.when(
      loading: () => const ShimmerList(count: 4, itemHeight: 92),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(pendingActionsStreamProvider)),
      data: (rawActions) {
        final actions = rawActions.map((a) => _enrichAction(a, productsCache)).toList();
        final critical = actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).toList();
        final others = actions.where((a) => (a['priority_score'] as int? ?? 0) < 85).toList();

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // ── Propuestas del staff — solo visibles para manager ─────────
            if (isManager && proposals.isNotEmpty) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF3E8FF),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF7C3AED).withValues(alpha: 0.3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Icon(Icons.pending_actions, color: Color(0xFF7C3AED), size: 16),
                      const SizedBox(width: 6),
                      Text('PROPUESTAS DEL PERSONAL (${proposals.length})',
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF7C3AED))),
                    ]),
                    const SizedBox(height: 10),
                    ...proposals.map((p) => _ProposalCard(
                      proposal: p,
                      onApprove: () async {
                        try {
                          await ApiService().approveAction(p['id'] as String);
                          ref.invalidate(_proposalsProvider);
                          ref.invalidate(pendingActionsStreamProvider);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Propuesta aprobada'), backgroundColor: Color(0xFF059669)),
                            );
                          }
                        } catch (e) {
                          if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
                        }
                      },
                      onOverride: () => onComplete(context, ref, p),
                      onReject: () async {
                        try {
                          await ApiService().rejectAction(p['id'] as String, 'Rechazada por el encargado');
                          ref.invalidate(_proposalsProvider);
                          ref.invalidate(pendingActionsStreamProvider);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Propuesta rechazada — vuelve a pendiente')),
                            );
                          }
                        } catch (e) {
                          if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
                        }
                      },
                    )),
                  ],
                ),
              ),
            ],

            if (actions.isEmpty && proposals.isEmpty)
              const Center(
                child: Padding(
                  padding: EdgeInsets.only(top: 80),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.check_circle, color: Color(0xFF059669), size: 64),
                    SizedBox(height: 16),
                    Text('Todo en orden', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                    SizedBox(height: 4),
                    Text('No hay acciones pendientes ahora mismo'),
                  ]),
                ),
              )
            else ...[
              Text('${actions.length} acciones pendientes',
                  style: const TextStyle(fontSize: 13, color: Colors.grey)),
              const SizedBox(height: 12),
              if (critical.isNotEmpty) ...[
                _SectionHeader(label: 'CRÍTICAS (${critical.length})', color: UrgencyColors.critical),
                ...critical.map((a) => _SwipeableActionCard(
                      action: a,
                      onComplete: () => onComplete(context, ref, a),
                      onDonate: () => onDonate(context, ref, a),
                    )),
                const SizedBox(height: 16),
              ],
              if (others.isNotEmpty) ...[
                _SectionHeader(label: 'OTRAS (${others.length})'),
                ...others.map((a) => _SwipeableActionCard(
                      action: a,
                      onComplete: () => onComplete(context, ref, a),
                      onDonate: () => onDonate(context, ref, a),
                    )),
              ],
            ],
          ],
        );
      },
    );
  }
}

// Tarjeta de propuesta — visible solo para manager
class _ProposalCard extends StatelessWidget {
  final Map<String, dynamic> proposal;
  final VoidCallback onApprove;
  final VoidCallback onOverride;
  final VoidCallback onReject;
  const _ProposalCard({required this.proposal, required this.onApprove, required this.onOverride, required this.onReject});

  @override
  Widget build(BuildContext context) {
    final notes = proposal['notes'] as String? ?? '';
    final batch = proposal['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';
    final currentType = proposal['action_type'] as String? ?? '';

    // Extraer tipo propuesto desde notes: "[PROPUESTA de staff: DONAR — motivo]"
    final proposedMatch = RegExp(r'\[PROPUESTA de (.+?):\s*(\w+)', caseSensitive: false).firstMatch(notes);
    final proposedBy = proposedMatch?.group(1) ?? (proposal['completed_by'] as String? ?? 'staff');
    final proposedType = proposedMatch?.group(2) ?? currentType;
    final reason = notes.replaceAll(RegExp(r'\[PROPUESTA[^\]]*\]'), '').trim();

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFF7C3AED).withValues(alpha: 0.2)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(productName, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700))),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
            decoration: BoxDecoration(color: const Color(0xFF7C3AED), borderRadius: BorderRadius.circular(5)),
            child: Text(proposedType.toUpperCase(), style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700)),
          ),
        ]),
        const SizedBox(height: 3),
        Text('Propuesto por: ${proposedBy.split('@').first}',
            style: const TextStyle(fontSize: 11, color: Colors.grey)),
        if (reason.isNotEmpty) Text(reason, style: const TextStyle(fontSize: 11, color: Color(0xFF4B5563))),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton(
            onPressed: onApprove,
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(0xFF059669),
              side: const BorderSide(color: Color(0xFF059669)),
              padding: const EdgeInsets.symmetric(vertical: 6),
            ),
            child: const Text('Aprobar', style: TextStyle(fontSize: 12)),
          )),
          const SizedBox(width: 6),
          Expanded(child: OutlinedButton(
            onPressed: onOverride,
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(0xFFF59E0B),
              side: const BorderSide(color: Color(0xFFF59E0B)),
              padding: const EdgeInsets.symmetric(vertical: 6),
            ),
            child: const Text('Decidir', style: TextStyle(fontSize: 12)),
          )),
          const SizedBox(width: 6),
          Expanded(child: OutlinedButton(
            onPressed: onReject,
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
              side: const BorderSide(color: Colors.red),
              padding: const EdgeInsets.symmetric(vertical: 6),
            ),
            child: const Text('Rechazar', style: TextStyle(fontSize: 12)),
          )),
        ]),
      ]),
    );
  }
}

// ── Historial Tab (rediseño) ──────────────────────────────────────────────────

const _typeColors = {
  'rebajar': Color(0xFFF59E0B),
  'donar': Color(0xFF7C3AED),
  'revisar': Color(0xFF3B82F6),
  'desechar': Color(0xFFEF4444),
  'mover': Color(0xFF059669),
};

const _typeIcons = {
  'rebajar': Icons.sell_outlined,
  'donar': Icons.volunteer_activism,
  'revisar': Icons.manage_search,
  'desechar': Icons.delete_outline,
  'mover': Icons.move_down,
};

Color _typeColor(String t) => _typeColors[t] ?? const Color(0xFF64748B);
IconData _typeIcon(String t) => _typeIcons[t] ?? Icons.check_circle_outline;

class _HistorialTab extends ConsumerStatefulWidget {
  const _HistorialTab();
  @override
  ConsumerState<_HistorialTab> createState() => _HistorialTabState();
}

class _HistorialTabState extends ConsumerState<_HistorialTab> {
  String _filterType = 'Todos';
  String _filterEmployee = 'Todos';

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(completedActionsProvider);
    return async.when(
      loading: () => const ShimmerList(count: 3, itemHeight: 72),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(completedActionsProvider)),
      data: (rawActions) {
        if (rawActions.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.history, size: 56, color: Colors.grey),
                SizedBox(height: 12),
                Text('Sin historial aún', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                SizedBox(height: 4),
                Text('Las acciones completadas aparecerán aquí', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey)),
              ]),
            ),
          );
        }

        // ── Stats globales ────────────────────────────────────────────────────
        final Map<String, int> byType = {};
        double totalValue = 0;
        final Set<String> employees = {};
        final Map<String, double> valueByDay = {};

        for (final a in rawActions) {
          final t = a['action_type'] as String? ?? 'revisar';
          byType[t] = (byType[t] ?? 0) + 1;
          final emp = a['completed_by'] as String? ?? 'Desconocido';
          employees.add(emp);
          final batch = a['batches'] as Map<String, dynamic>?;
          final product = batch?['products'] as Map<String, dynamic>?;
          final qty = (batch?['quantity'] as num?)?.toDouble() ?? 1;
          final price = (product?['price'] as num?)?.toDouble() ?? 0;
          totalValue += qty * price;
          final completedAt = a['completed_at'] as String? ?? '';
          if (completedAt.isNotEmpty) {
            try {
              final dt = DateTime.parse(completedAt).toLocal();
              final dayKey = '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}';
              valueByDay[dayKey] = (valueByDay[dayKey] ?? 0) + qty * price;
            } catch (_) {}
          }
        }

        // ── Filtrar ───────────────────────────────────────────────────────────
        final filtered = rawActions.where((a) {
          final t = a['action_type'] as String? ?? 'revisar';
          final emp = a['completed_by'] as String? ?? 'Desconocido';
          if (_filterType != 'Todos' && t != _filterType) return false;
          if (_filterEmployee != 'Todos' && emp != _filterEmployee) return false;
          return true;
        }).toList();

        // ── Agrupar por fecha ─────────────────────────────────────────────────
        final Map<String, List<Map<String, dynamic>>> byDate = {};
        for (final a in filtered) {
          final completedAt = a['completed_at'] as String? ?? '';
          String dateKey = 'Sin fecha';
          if (completedAt.isNotEmpty) {
            try {
              final dt = DateTime.parse(completedAt).toLocal();
              final now = DateTime.now();
              final today = DateTime(now.year, now.month, now.day);
              final day = DateTime(dt.year, dt.month, dt.day);
              if (day == today) {
                dateKey = 'Hoy';
              } else if (day == today.subtract(const Duration(days: 1))) {
                dateKey = 'Ayer';
              } else {
                dateKey = '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year}';
              }
            } catch (_) {}
          }
          byDate.putIfAbsent(dateKey, () => []).add(a);
        }

        final typeFilters = ['Todos', ...byType.keys];
        final empFilters = ['Todos', ...employees];

        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(completedActionsProvider),
          child: ListView(
            padding: const EdgeInsets.all(14),
            children: [
              // ── Header stats ─────────────────────────────────────────────
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF059669), Color(0xFF047857)],
                    begin: Alignment.topLeft, end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Historial — últimos 30 días',
                      style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 14),
                  Row(children: [
                    _HistStat('${rawActions.length}', 'acciones', Icons.check_circle_outline),
                    const SizedBox(width: 10),
                    _HistStat('${totalValue.toStringAsFixed(0)} €', 'recuperado', Icons.euro),
                    const SizedBox(width: 10),
                    _HistStat('${byType['donar'] ?? 0}', 'donaciones', Icons.volunteer_activism),
                    const SizedBox(width: 10),
                    _HistStat('${employees.length}', 'empleados', Icons.people_outline),
                  ]),
                  const SizedBox(height: 14),
                  // Mini barras por tipo
                  Wrap(spacing: 6, runSpacing: 6, children: byType.entries.map((e) {
                    final color = _typeColor(e.key);
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: color.withValues(alpha: 0.4)),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(_typeIcon(e.key), size: 12, color: Colors.white),
                        const SizedBox(width: 4),
                        Text('${e.key.toUpperCase()} · ${e.value}',
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white)),
                      ]),
                    );
                  }).toList()),
                ]),
              ),
              const SizedBox(height: 12),

              // ── Mini chart de valor por día ────────────────────────────────
              if (valueByDay.isNotEmpty) _ValueBarChart(valueByDay: valueByDay),
              const SizedBox(height: 12),

              // ── Filtros ───────────────────────────────────────────────────
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  const Text('Tipo:', style: TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.w600)),
                  const SizedBox(width: 8),
                  ...typeFilters.map((t) => _HistChip(
                    label: t == 'Todos' ? 'Todos' : t,
                    selected: _filterType == t,
                    color: t == 'Todos' ? const Color(0xFF059669) : _typeColor(t),
                    onTap: () => setState(() => _filterType = t),
                  )),
                  const SizedBox(width: 16),
                  if (empFilters.length > 2) ...[
                    const Text('Empleado:', style: TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.w600)),
                    const SizedBox(width: 8),
                    ...empFilters.take(4).map((e) {
                      final display = e == 'Todos' ? 'Todos' : (e.contains('@') ? e.split('@').first : e);
                      return _HistChip(
                        label: display.length > 10 ? '${display.substring(0, 8)}…' : display,
                        selected: _filterEmployee == e,
                        color: const Color(0xFF6366F1),
                        onTap: () => setState(() => _filterEmployee = e),
                      );
                    }),
                  ],
                ]),
              ),
              const SizedBox(height: 10),

              Text('${filtered.length} de ${rawActions.length} acciones',
                  style: const TextStyle(fontSize: 12, color: Colors.grey)),
              const SizedBox(height: 10),

              // ── Timeline por fecha ────────────────────────────────────────
              ...byDate.entries.map((e) => _DateSection(date: e.key, actions: e.value)),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }
}

class _HistStat extends StatelessWidget {
  final String value, label;
  final IconData icon;
  const _HistStat(this.value, this.label, this.icon);
  @override
  Widget build(BuildContext context) => Expanded(child: Container(
    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 6),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Column(children: [
      Icon(icon, color: Colors.white, size: 16),
      const SizedBox(height: 3),
      Text(value, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w800)),
      Text(label, style: const TextStyle(color: Colors.white70, fontSize: 9), textAlign: TextAlign.center),
    ]),
  ));
}

class _HistChip extends StatelessWidget {
  final String label;
  final bool selected;
  final Color color;
  final VoidCallback onTap;
  const _HistChip({required this.label, required this.selected, required this.color, required this.onTap});
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      margin: const EdgeInsets.only(right: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: selected ? color : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: selected ? Colors.transparent : const Color(0xFFE5E7EB)),
      ),
      child: Text(label, style: TextStyle(
          fontSize: 11, fontWeight: FontWeight.w600,
          color: selected ? Colors.white : color)),
    ),
  );
}

class _ValueBarChart extends StatelessWidget {
  final Map<String, double> valueByDay;
  const _ValueBarChart({required this.valueByDay});

  @override
  Widget build(BuildContext context) {
    final entries = valueByDay.entries.toList()..sort((a, b) => a.key.compareTo(b.key));
    final last7 = entries.length > 7 ? entries.sublist(entries.length - 7) : entries;
    final maxVal = last7.fold(0.0, (m, e) => e.value > m ? e.value : m);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Valor recuperado por día', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF374151))),
        const SizedBox(height: 12),
        SizedBox(
          height: 64,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: last7.map((e) {
              final frac = maxVal > 0 ? (e.value / maxVal).clamp(0.05, 1.0) : 0.05;
              return Expanded(child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  Text('${e.value.toStringAsFixed(0)}€',
                      style: const TextStyle(fontSize: 7, color: Colors.grey)),
                  const SizedBox(height: 2),
                  Container(
                    height: 50 * frac,
                    decoration: BoxDecoration(
                      color: const Color(0xFF059669),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(e.key.substring(0, 5), style: const TextStyle(fontSize: 7, color: Colors.grey)),
                ]),
              ));
            }).toList(),
          ),
        ),
      ]),
    );
  }
}

class _DateSection extends StatelessWidget {
  final String date;
  final List<Map<String, dynamic>> actions;
  const _DateSection({required this.date, required this.actions});

  @override
  Widget build(BuildContext context) {
    double sectionValue = 0;
    for (final a in actions) {
      final batch = a['batches'] as Map<String, dynamic>?;
      final product = batch?['products'] as Map<String, dynamic>?;
      final qty = (batch?['quantity'] as num?)?.toDouble() ?? 1;
      final price = (product?['price'] as num?)?.toDouble() ?? 0;
      sectionValue += qty * price;
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 8, top: 4),
        child: Row(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF059669),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(date, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 8),
          Text('${actions.length} acciones', style: const TextStyle(fontSize: 11, color: Colors.grey)),
          const Spacer(),
          Text('${sectionValue.toStringAsFixed(2)} €',
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF059669))),
        ]),
      ),
      ...actions.map((a) => _CompletedActionCard(action: a)),
      const SizedBox(height: 10),
    ]);
  }
}

class _CompletedActionCard extends StatelessWidget {
  final Map<String, dynamic> action;
  const _CompletedActionCard({required this.action});

  @override
  Widget build(BuildContext context) {
    final actionType = action['action_type'] as String? ?? 'revisar';
    final notes = action['notes'] as String? ?? '';
    final completedAt = action['completed_at'] as String? ?? '';
    final photoUrl = action['photo_url'] as String? ?? '';
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';
    final cat = product?['category'] as String? ?? '';
    final qty = (batch?['quantity'] as num?)?.toInt() ?? 1;
    final price = (product?['price'] as num?)?.toDouble() ?? 0;
    final value = qty * price;
    final emp = action['completed_by'] as String? ?? '';
    final displayEmp = emp.contains('@') ? emp.split('@').first : emp;

    String timeLabel = '';
    if (completedAt.isNotEmpty) {
      try {
        final dt = DateTime.parse(completedAt).toLocal();
        timeLabel = '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      } catch (_) {}
    }

    final typeColor = _typeColor(actionType);
    final typeIcon = _typeIcon(actionType);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: typeColor, width: 3)),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4, offset: const Offset(0, 2))],
      ),
      child: Row(children: [
        Container(
          width: 36, height: 36,
          decoration: BoxDecoration(
            color: typeColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(9),
          ),
          child: Icon(typeIcon, color: typeColor, size: 18),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(productName, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: typeColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(actionType.toUpperCase(),
                  style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: typeColor)),
            ),
            if (cat.isNotEmpty) ...[
              const SizedBox(width: 6),
              Text(cat, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ],
            if (displayEmp.isNotEmpty) ...[
              const SizedBox(width: 6),
              Text('· $displayEmp', style: const TextStyle(fontSize: 10, color: Colors.grey)),
            ],
          ]),
          if (notes.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(notes, style: const TextStyle(fontSize: 11, color: Colors.grey),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
        ])),
        const SizedBox(width: 8),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          if (value > 0)
            Text('${value.toStringAsFixed(2)} €',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF059669))),
          Text(timeLabel, style: const TextStyle(fontSize: 10, color: Colors.grey)),
          if (photoUrl.isNotEmpty)
            GestureDetector(
              onTap: () => _showPhoto(context, photoUrl),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(5),
                child: Image.network(photoUrl, width: 32, height: 32, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const Icon(Icons.broken_image_outlined, size: 18, color: Colors.grey)),
              ),
            )
          else
            const Icon(Icons.check_circle, color: Color(0xFF059669), size: 18),
        ]),
      ]),
    );
  }

  void _showPhoto(BuildContext context, String url) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text('Foto evidencia', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          ),
          Image.network(url, fit: BoxFit.contain),
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
        ]),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;
  final Color color;

  const _SectionHeader({required this.label, this.color = Colors.grey});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          color: color,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

// ── Swipeable wrapper — desliza para completar o donar ────────────────────────
// Deslizar derecha → completar (✅ verde)
// Deslizar izquierda → donar (❤️ morado)
// Con haptic feedback en cada dirección.

class _SwipeableActionCard extends ConsumerWidget {
  final Map<String, dynamic> action;
  final VoidCallback onComplete;
  final VoidCallback onDonate;

  const _SwipeableActionCard({
    required this.action,
    required this.onComplete,
    required this.onDonate,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final role = ref.watch(userRoleProvider).valueOrNull ?? UserRole.staff;
    final actionId = action['id']?.toString() ?? UniqueKey().toString();
    return Dismissible(
      key: ValueKey(actionId),
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: role.index >= UserRole.manager.index
              ? const Color(0xFF059669)
              : Colors.grey[400]!,
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerLeft,
        child: const Row(children: [
          Icon(Icons.check_circle_rounded, color: Colors.white, size: 28),
          SizedBox(width: 10),
          Text('Completar', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15)),
        ]),
      ),
      secondaryBackground: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF7C3AED),
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerRight,
        child: const Row(mainAxisAlignment: MainAxisAlignment.end, children: [
          Text('Donar', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15)),
          SizedBox(width: 10),
          Icon(Icons.favorite_rounded, color: Colors.white, size: 28),
        ]),
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          if (role.index < UserRole.manager.index) {
            HapticFeedback.vibrate();
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Solo los encargados pueden confirmar acciones. Avisa a tu responsable.'),
              backgroundColor: Color(0xFFF59E0B),
              duration: Duration(seconds: 3),
            ));
            return false;
          }
          HapticFeedback.mediumImpact();
          onComplete();
          return false;
        } else {
          HapticFeedback.selectionClick();
          if (role.index < UserRole.manager.index) {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Usa el botón "Proponer donación" para enviarla al encargado.'),
              backgroundColor: Color(0xFF7C3AED),
              duration: Duration(seconds: 3),
            ));
            return false;
          }
          onDonate();
          return false;
        }
      },
      child: _ActionCard(action: action, onComplete: onComplete, onDonate: onDonate),
    );
  }
}

class _NotesParsed {
  final String? name;
  final String? pasillo;
  final String? estanteria;
  final String? nivel;
  const _NotesParsed({this.name, this.pasillo, this.estanteria, this.nivel});
}

class _ActionCard extends ConsumerWidget {
  final Map<String, dynamic> action;
  final VoidCallback onComplete;
  final VoidCallback onDonate;

  const _ActionCard({
    required this.action,
    required this.onComplete,
    required this.onDonate,
  });

  // Parse product name and location from notes when product join is null.
  // Handles two formats:
  //   "Yogur Danone x4 (Pasillo 2-E3-N1)."
  //   "CRÍTICO. Salmón ahumado 100g (pasillo 4, est. 2, nivel 1). ..."
  static _NotesParsed _parseNotes(String notes) {
    // Format 1: "Pasillo X-EY-NZ"
    final loc1 = RegExp(r'[Pp]asillo\s+(\w+)-E(\w+)-N(\w+)').firstMatch(notes);
    // Format 2: "(pasillo X, est. Y, nivel Z)"
    final loc2 = RegExp(r'\(\s*pasillo\s+(\w+),\s*est\.?\s*(\w+),\s*nivel\s*(\w+)', caseSensitive: false).firstMatch(notes);
    final locMatch = loc1 ?? loc2;

    // Strip leading "CRÍTICO." / "URGENTE." prefix before extracting name
    final stripped = notes.replaceFirst(RegExp(r'^(CR[IÍ]TICO|URGENTE|ALTO|MEDIO|BAJO)\.\s*', caseSensitive: false), '');
    final nameMatch = RegExp(r'^(.+?)\s*\(').firstMatch(stripped);

    return _NotesParsed(
      name: nameMatch?.group(1)?.trim(),
      pasillo: locMatch?.group(1),
      estanteria: locMatch?.group(2),
      nivel: locMatch?.group(3),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final role = ref.watch(userRoleProvider).valueOrNull ?? UserRole.staff;
    final canConfirm = role.index >= UserRole.manager.index;

    final score = action['priority_score'] as int? ?? 0;
    final actionType = action['action_type'] as String? ?? '';
    final notes = action['notes'] as String? ?? '';
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;

    final parsed = _parseNotes(notes);
    final productName = product?['name'] as String? ?? parsed.name ?? 'Producto';
    final pasillo = product?['pasillo'] as String? ?? parsed.pasillo;
    final estanteria = product?['estanteria'] as String? ?? parsed.estanteria;
    final nivel = product?['nivel'] as String? ?? parsed.nivel;
    final expiryDate = batch?['expiry_date'] as String?;
    final quantity = batch?['quantity'] as int? ?? 0;

    int daysLeft = 999;
    if (expiryDate != null) {
      try {
        daysLeft = DateTime.parse(expiryDate).difference(DateTime.now()).inDays;
      } catch (_) {}
    }

    final urgencyColor = UrgencyColors.forDays(daysLeft);
    final actionColor = _actionColor(actionType);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: urgencyColor.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: urgencyColor.withValues(alpha: 0.08),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: actionColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    actionType.toUpperCase(),
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: actionColor,
                    ),
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: urgencyColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '$score/100',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: urgencyColor,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              productName,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                Icon(Icons.location_on_outlined, size: 13, color: Colors.grey[500]),
                const SizedBox(width: 3),
                Text(
                  [
                    _pasilloLabel(pasillo),
                    if (estanteria != null) 'E$estanteria',
                    if (nivel != null) 'N$nivel',
                  ].join(' · '),
                  style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                ),
                const Spacer(),
                if (expiryDate != null)
                  Text(
                    daysLeft <= 0
                        ? 'Caduca HOY'
                        : daysLeft == 1
                            ? 'Caduca mañana'
                            : 'Caduca en $daysLeft días',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: urgencyColor,
                    ),
                  ),
              ],
            ),
            if (quantity > 0) ...[
              const SizedBox(height: 4),
              Text(
                'Stock: $quantity uds',
                style: TextStyle(fontSize: 12, color: Colors.grey[600]),
              ),
            ],
            if (notes.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                notes,
                style: const TextStyle(fontSize: 12, color: Color(0xFF4B5563)),
              ),
            ],
            const SizedBox(height: 10),
            if (actionType == 'rebajar') ...[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.label_outline, size: 16),
                  label: const Text('Ver etiqueta de descuento'),
                  onPressed: () => _showDiscountLabel(context, action),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFFF59E0B),
                    side: const BorderSide(color: Color(0xFFF59E0B)),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              const SizedBox(height: 8),
            ],
            if (actionType == 'rebajar' || actionType == 'retirar') ...[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.volunteer_activism, size: 16),
                  label: Text(canConfirm ? 'Donar en su lugar' : 'Proponer donación'),
                  onPressed: canConfirm
                      ? onDonate
                      : () => _showProposeSheet(
                            context,
                            Map<String, dynamic>.from(action)..['action_type'] = 'donar',
                          ),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFF059669),
                    side: const BorderSide(
                        color: Color(0xFF059669), style: BorderStyle.solid),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    backgroundColor: const Color(0xFFF0FDF4),
                  ),
                ),
              ),
              const SizedBox(height: 8),
            ],
            if (canConfirm) ...[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.check, size: 16),
                  label: Text(actionType == 'rebajar'
                      ? 'Confirmar rebaja'
                      : actionType == 'retirar'
                          ? 'Confirmar retirada'
                          : 'Marcar completada'),
                  onPressed: onComplete,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.grey[700],
                    side: BorderSide(color: Colors.grey[400]!),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
            ] else ...[
              // Staff: proponer una acción al encargado
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.send_outlined, size: 16),
                  label: const Text('Proponer al encargado'),
                  onPressed: () => _showProposeSheet(context, action),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF7C3AED),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Color _actionColor(String type) {
    switch (type) {
      case 'retirar':
        return UrgencyColors.critical;
      case 'rebajar':
        return UrgencyColors.high;
      case 'donar':
        return UrgencyColors.medium;
      case 'reponer':
        return const Color(0xFF059669);
      default:
        return Colors.grey;
    }
  }

  void _showDiscountLabel(BuildContext context, Map<String, dynamic> action) {
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';
    final originalPrice = (product?['price'] as num?)?.toDouble() ?? 0;
    final cost = (product?['cost'] as num?)?.toDouble() ?? 0;
    final expiryDate = batch?['expiry_date'] as String? ?? '';
    final actionId = action['id'] as String? ?? '';

    int discountPct = (action['price_adjustment_pct'] as int?) ?? 0;
    if (discountPct == 0) {
      final notes = action['notes'] as String? ?? '';
      final match = RegExp(r'(\d+)\s*%').firstMatch(notes);
      if (match != null) discountPct = int.tryParse(match.group(1) ?? '') ?? 30;
    }
    if (discountPct == 0) discountPct = 30;

    final newPrice = (action['new_price'] as num?)?.toDouble() ??
        (originalPrice * (1 - discountPct / 100));

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _DiscountLabelSheet(
        productName: productName,
        originalPrice: originalPrice,
        newPrice: newPrice,
        cost: cost,
        discountPct: discountPct,
        expiryDate: expiryDate,
        actionId: actionId,
      ),
    );
  }

  void _showProposeSheet(BuildContext context, Map<String, dynamic> action) {
    final actionId = action['id'] as String? ?? '';
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';
    final currentType = action['action_type'] as String? ?? 'revisar';

    String selectedType = currentType;
    final reasonCtrl = TextEditingController();
    bool sending = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => Padding(
          padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(ctx).viewInsets.bottom + 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.send_outlined, color: Color(0xFF7C3AED)),
                const SizedBox(width: 8),
                Expanded(child: Text('Proponer acción — $productName',
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
              ]),
              const SizedBox(height: 4),
              const Text('El encargado recibirá tu propuesta y decidirá.',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
              const SizedBox(height: 16),
              const Text('¿Qué propones hacer?',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final t in ['rebajar', 'donar', 'retirar', 'mover', 'revisar'])
                  ChoiceChip(
                    label: Text(t.toUpperCase()),
                    selected: selectedType == t,
                    onSelected: (_) => setState(() => selectedType = t),
                    selectedColor: const Color(0xFF7C3AED).withValues(alpha: 0.2),
                    labelStyle: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: selectedType == t ? const Color(0xFF7C3AED) : Colors.grey[600],
                    ),
                  ),
              ]),
              const SizedBox(height: 14),
              TextField(
                controller: reasonCtrl,
                maxLines: 2,
                decoration: InputDecoration(
                  hintText: 'Motivo o nota para el encargado (opcional)',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                  contentPadding: const EdgeInsets.all(12),
                  filled: true,
                  fillColor: const Color(0xFFF9FAFB),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  icon: sending
                      ? const SizedBox(width: 16, height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.send, size: 16),
                  label: const Text('Enviar propuesta'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF7C3AED),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13),
                  ),
                  onPressed: sending ? null : () async {
                    setState(() => sending = true);
                    try {
                      await ApiService().proposeAction(actionId, selectedType, reasonCtrl.text.trim());
                      if (ctx.mounted) {
                        Navigator.pop(ctx);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text('Propuesta enviada: $selectedType para $productName'),
                            backgroundColor: const Color(0xFF7C3AED),
                          ),
                        );
                      }
                    } catch (e) {
                      setState(() => sending = false);
                      if (ctx.mounted) {
                        ScaffoldMessenger.of(ctx).showSnackBar(
                          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
                        );
                      }
                    }
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DiscountLabelSheet extends StatefulWidget {
  final String productName;
  final double originalPrice;
  final double newPrice;
  final double cost;
  final int discountPct;
  final String expiryDate;
  final String actionId;

  const _DiscountLabelSheet({
    required this.productName,
    required this.originalPrice,
    required this.newPrice,
    this.cost = 0.0,
    required this.discountPct,
    required this.expiryDate,
    required this.actionId,
  });

  @override
  State<_DiscountLabelSheet> createState() => _DiscountLabelSheetState();
}

class _DiscountLabelSheetState extends State<_DiscountLabelSheet> {
  bool _downloading = false;
  late double _customDiscount;  // 0.0 - 0.70

  @override
  void initState() {
    super.initState();
    _customDiscount = (widget.discountPct / 100.0).clamp(0.0, 0.70);
  }

  double get _customPrice {
    if (widget.originalPrice <= 0) return widget.newPrice;
    final raw = widget.originalPrice * (1 - _customDiscount);
    return (raw / 0.05).round() * 0.05;  // redondeo comercial .x0/.x5
  }

  int get _effectiveDiscountPct =>
      widget.originalPrice > 0
          ? ((_customDiscount) * 100).round()
          : widget.discountPct;

  Color get _marginColor {
    if (widget.cost <= 0) return const Color(0xFF059669);
    if (_customPrice < widget.cost * 1.05) return const Color(0xFFEF4444);
    if (_customPrice < widget.cost * 1.15) return const Color(0xFFF59E0B);
    return const Color(0xFF059669);
  }

  String get _marginLabel {
    if (widget.cost <= 0) return '';
    final margin = _customPrice - widget.cost;
    if (_customPrice < widget.cost * 1.05) return 'Por debajo del coste — sube el precio';
    return 'Margen: ${margin.toStringAsFixed(2)} €/ud';
  }

  Future<void> _downloadPdf() async {
    if (_downloading) return;
    setState(() => _downloading = true);
    try {
      final bytes = await api.getPriceLabel(widget.actionId);
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/etiqueta_${widget.actionId.substring(0, 8)}.pdf');
      await file.writeAsBytes(bytes);
      await Share.shareXFiles([XFile(file.path)], text: '🏷️ Etiqueta de descuento: ${widget.productName}');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error descargando PDF: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 32),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Etiqueta de descuento',
              style: TextStyle(fontSize: 14, color: Colors.grey),
            ),
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFFFFFBEB),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFFFCD34D), width: 2),
              ),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEF4444),
                      borderRadius: BorderRadius.circular(30),
                    ),
                    child: Text(
                      '-${widget.discountPct}%',
                      style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w900),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    widget.productName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (widget.originalPrice > 0) ...[
                        Text(
                          '${widget.originalPrice.toStringAsFixed(2)} €',
                          style: const TextStyle(fontSize: 16, color: Colors.grey, decoration: TextDecoration.lineThrough),
                        ),
                        const SizedBox(width: 12),
                      ],
                      Text(
                        '${widget.newPrice.toStringAsFixed(2)} €',
                        style: const TextStyle(fontSize: 36, fontWeight: FontWeight.w900, color: Color(0xFFEF4444), letterSpacing: -1),
                      ),
                    ],
                  ),
                  if (widget.expiryDate.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      decoration: BoxDecoration(color: const Color(0xFFFEE2E2), borderRadius: BorderRadius.circular(6)),
                      child: Text(
                        'Caduca: ${widget.expiryDate}',
                        style: const TextStyle(fontSize: 12, color: Color(0xFF991B1B), fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  const Text('Precio especial por proximidad a caducidad',
                      textAlign: TextAlign.center, style: TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ),
            ),
            // ── Slider de ajuste manual del descuento ──────────────────────
            if (widget.originalPrice > 0) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF9FAFB),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Ajustar descuento',
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF374151))),
                        Text('$_effectiveDiscountPct% → ${_customPrice.toStringAsFixed(2)} €',
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: Color(0xFFEF4444))),
                      ],
                    ),
                    Slider(
                      value: _customDiscount,
                      min: 0.10,
                      max: 0.70,
                      divisions: 12,
                      activeColor: _marginColor,
                      onChanged: (v) => setState(() => _customDiscount = v),
                    ),
                    if (_marginLabel.isNotEmpty)
                      Text(_marginLabel,
                          style: TextStyle(fontSize: 11, color: _marginColor, fontWeight: FontWeight.w500)),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 8),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Cerrar'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.share_outlined, size: 18),
                    label: const Text('Compartir'),
                    onPressed: () {
                      Navigator.pop(context);
                      final text = '🏷️ OFERTA — ${widget.productName}\n'
                          '${widget.originalPrice > 0 ? 'Antes: ${widget.originalPrice.toStringAsFixed(2)} €\n' : ''}'
                          '-${widget.discountPct}% DESCUENTO\n'
                          'Ahora: ${widget.newPrice.toStringAsFixed(2)} €\n'
                          '${widget.expiryDate.isNotEmpty ? 'Caduca: ${widget.expiryDate}\n' : ''}'
                          'Precio especial por proximidad a caducidad.';
                      Share.share(text);
                    },
                    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFF59E0B), foregroundColor: Colors.white),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton.icon(
                  icon: _downloading
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.download_rounded, size: 18),
                  label: const Text('PDF'),
                  onPressed: widget.actionId.isEmpty ? null : _downloadPdf,
                  style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF059669), foregroundColor: Colors.white),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── Daily progress header ─────────────────────────────────────────────────────

class _DailyProgressHeader extends ConsumerWidget {
  final AsyncValue actionsAsync;
  const _DailyProgressHeader({required this.actionsAsync});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final completedAsync = ref.watch(completedActionsProvider);

    final pending = actionsAsync.when(
      data: (a) => (a as List).length,
      loading: () => 0,
      error: (_, __) => 0,
    );
    final completed = completedAsync.when(
      data: (a) => a.length,
      loading: () => 0,
      error: (_, __) => 0,
    );
    final total = pending + completed;
    final pct = total == 0 ? 0.0 : completed / total;

    final barColor = pct >= 1.0
        ? const Color(0xFF059669)
        : pct >= 0.5
            ? const Color(0xFF3B82F6)
            : const Color(0xFFF59E0B);

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Color(0xFFE2E8F0))),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.today_rounded, size: 15, color: Colors.grey[500]),
          const SizedBox(width: 6),
          Text('Progreso del día',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.grey[700])),
          const Spacer(),
          Text('$completed / $total acciones',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: pct >= 1.0 ? const Color(0xFF059669) : Colors.grey[600])),
        ]),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: pct,
            minHeight: 7,
            backgroundColor: const Color(0xFFE5E7EB),
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
          ),
        ),
        if (pct >= 1.0)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(children: const [
              Icon(Icons.check_circle_rounded, color: Color(0xFF059669), size: 12),
              SizedBox(width: 4),
              Text('¡Todo el trabajo de hoy completado!',
                  style: TextStyle(fontSize: 10, color: Color(0xFF059669), fontWeight: FontWeight.w600)),
            ]),
          ),
      ]),
    );
  }
}
