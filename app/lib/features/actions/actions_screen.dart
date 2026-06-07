import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_service.dart';
import '../../core/error_widget.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart' show UrgencyColors, ShimmerList;
import 'actions_provider.dart';

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
    final actionsAsync = ref.watch(pendingActionsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Acciones'),
        actions: [
          IconButton(
            icon: const Icon(Icons.upload_file_outlined),
            tooltip: 'Importar CSV',
            onPressed: () => _showImportDialog(context),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.invalidate(pendingActionsProvider);
              ref.invalidate(completedActionsProvider);
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
      body: TabBarView(
        controller: _tabs,
        children: [
          _PendingTab(
            onComplete: _showCompleteDialog,
            onDonate: _showDonateDialog,
          ),
          const _HistorialTab(),
        ],
      ),
    );
  }

  void _showImportDialog(BuildContext context) {
    final controller = TextEditingController(
      text: 'barcode,quantity,expiry_date\n'
          '8410001000001,10,2026-06-15\n'
          '8410031001001,5,2026-06-10\n',
    );
    // State declared outside builder so it persists across setState calls
    var loading = false;
    String? result;
    var resultIsError = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) => Padding(
          padding: EdgeInsets.fromLTRB(
              16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.upload_file, color: Color(0xFF059669)),
                  SizedBox(width: 8),
                  Text(
                    'Importar CSV desde TPV',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Columnas: barcode, quantity, expiry_date (YYYY-MM-DD)',
                style: TextStyle(fontSize: 11, color: Colors.grey),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                maxLines: 6,
                style:
                    const TextStyle(fontSize: 12, fontFamily: 'monospace'),
                decoration: InputDecoration(
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8)),
                  filled: true,
                  fillColor: const Color(0xFFF9FAFB),
                  contentPadding: const EdgeInsets.all(10),
                ),
              ),
              if (result != null) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: resultIsError
                        ? const Color(0xFFFEE2E2)
                        : const Color(0xFFD1FAE5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    result!,
                    style: TextStyle(
                      fontSize: 12,
                      color: resultIsError
                          ? const Color(0xFFDC2626)
                          : const Color(0xFF059669),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('Cancelar'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton.icon(
                    icon: loading
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.upload, size: 16),
                    label: const Text('Importar'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF059669),
                      foregroundColor: Colors.white,
                    ),
                    onPressed: loading
                        ? null
                        : () async {
                            setModalState(() => loading = true);
                            try {
                              final res =
                                  await api.importBatches(controller.text);
                              final imp = res['imported'] as int? ?? 0;
                              final err = res['errors'] as int? ?? 0;
                              setModalState(() {
                                result = 'Importados: $imp lotes'
                                    '${err > 0 ? ' · $err errores' : ''}.';
                                resultIsError = false;
                                loading = false;
                              });
                              if (imp > 0) {
                                ref.invalidate(pendingActionsProvider);
                              }
                            } catch (e) {
                              setModalState(() {
                                result = friendlyError(e);
                                resultIsError = true;
                                loading = false;
                              });
                            }
                          },
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
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
    final userId = supabase.auth.currentUser?.id ?? 'unknown';
    final userLabel = supabase.auth.currentUser?.email ?? userId;
    final actionId = action['id'] as String;
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? '';
    final price = (product?['price'] as num?)?.toDouble() ?? 0;

    try {
      final nowUtc = DateTime.now().toUtc().toIso8601String();
      // Mark action completed — completed_by stores email for legible historial
      await supabase.from('actions').update({
        'status': 'completed',
        'completed_by': userLabel,
        'completed_at': nowUtc,
        'notes': notes.isEmpty ? 'Donado a $entity — $quantity uds' : notes,
        'donation_entity': entity,
        'donation_quantity': quantity,
      }).eq('id', actionId);

      // Register in donations table (donated_at required for stats queries)
      await supabase.from('donations').insert({
        'store_id': storeId,
        'batch_id': action['batch_id'],
        'action_id': actionId,
        'entity': entity,
        'quantity': quantity,
        'product_name': productName,
        'value_donated': (price * quantity),
        'donated_by': userLabel,
        'donated_at': nowUtc,
        'notes': notes,
      });
    } catch (_) {
      // Fallback: si falla la escritura directa a Supabase, completa vía API backend
      await api.completeAction(
        actionId: actionId,
        completedBy: userLabel,
        notes: 'Donado a $entity — $quantity uds',
      );
      // Si este segundo intento también falla, deja que la excepción llegue al caller
    }
    ref.invalidate(pendingActionsProvider);
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
      await supabase.from('actions').update({
        'status': 'completed',
        'completed_by': userId,
        'completed_at': DateTime.now().toUtc().toIso8601String(),
        'notes': notes,
        if (photoUrl.isNotEmpty) 'photo_url': photoUrl,
      }).eq('id', actionId);
      synced = true;
    } catch (_) {
      try {
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
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Sin conexión — acción guardada. Se sincronizará automáticamente.'),
            backgroundColor: Color(0xFFF59E0B),
            duration: Duration(seconds: 4),
          ));
        }
      }
    }
    if (synced) {
      ref.invalidate(pendingActionsProvider);
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
        ref.invalidate(pendingActionsProvider);
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
    final actionsAsync = ref.watch(pendingActionsProvider);
    return actionsAsync.when(
      loading: () => const ShimmerList(count: 4, itemHeight: 92),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(pendingActionsProvider)),
      data: (actions) {
        if (actions.isEmpty) {
          return const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.check_circle, color: Color(0xFF059669), size: 64),
                SizedBox(height: 16),
                Text(
                  'Todo en orden',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
                ),
                SizedBox(height: 4),
                Text('No hay acciones pendientes ahora mismo'),
              ],
            ),
          );
        }

        final critical =
            actions.where((a) => (a['priority_score'] as int? ?? 0) >= 85).toList();
        final others =
            actions.where((a) => (a['priority_score'] as int? ?? 0) < 85).toList();

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              '${actions.length} acciones pendientes',
              style: const TextStyle(fontSize: 13, color: Colors.grey),
            ),
            const SizedBox(height: 12),
            if (critical.isNotEmpty) ...[
              _SectionHeader(
                label: 'CRÍTICAS (${critical.length})',
                color: UrgencyColors.critical,
              ),
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
        );
      },
    );
  }
}

class _HistorialTab extends ConsumerWidget {
  const _HistorialTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(completedActionsProvider);
    return async.when(
      loading: () => const ShimmerList(count: 3, itemHeight: 72),
      error: (e, _) => AppErrorWidget(error: e, onRetry: () => ref.invalidate(completedActionsProvider)),
      data: (actions) {
        if (actions.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.history, size: 48, color: Colors.grey),
                  SizedBox(height: 12),
                  Text(
                    'Sin historial aún',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Las acciones completadas aparecerán aquí',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        }

        // Group by employee
        final Map<String, List<Map<String, dynamic>>> byEmployee = {};
        for (final a in actions) {
          final emp = a['completed_by'] as String? ?? 'Desconocido';
          byEmployee.putIfAbsent(emp, () => []).add(a);
        }

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              '${actions.length} acciones completadas (últimos 30 días)',
              style: const TextStyle(fontSize: 13, color: Colors.grey),
            ),
            const SizedBox(height: 12),
            ...byEmployee.entries.map((entry) {
              final emp = entry.key;
              final empActions = entry.value;
              return _EmployeeSection(employee: emp, actions: empActions);
            }),
          ],
        );
      },
    );
  }
}

class _EmployeeSection extends StatelessWidget {
  final String employee;
  final List<Map<String, dynamic>> actions;

  const _EmployeeSection({required this.employee, required this.actions});

  @override
  Widget build(BuildContext context) {
    // If it looks like an email, show only the local part (before @)
    final displayName = employee.contains('@')
        ? employee.split('@').first
        : (employee.length > 20 ? '${employee.substring(0, 8)}…' : employee);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            children: [
              CircleAvatar(
                radius: 14,
                backgroundColor: const Color(0xFF059669).withValues(alpha: 0.15),
                child: Text(
                  displayName.isNotEmpty
                      ? displayName[0].toUpperCase()
                      : '?',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF059669),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                displayName,
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              ),
              const SizedBox(width: 6),
              Text(
                '${actions.length} acciones',
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
        ),
        ...actions.map((a) => _CompletedActionRow(action: a)),
        const SizedBox(height: 16),
      ],
    );
  }
}

class _CompletedActionRow extends StatelessWidget {
  final Map<String, dynamic> action;

  const _CompletedActionRow({required this.action});

  @override
  Widget build(BuildContext context) {
    final actionType = action['action_type'] as String? ?? '';
    final notes = action['notes'] as String? ?? '';
    final completedAt = action['completed_at'] as String? ?? '';
    final photoUrl = action['photo_url'] as String? ?? '';
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;
    final productName = product?['name'] as String? ?? 'Producto';

    String timeLabel = '';
    if (completedAt.isNotEmpty) {
      try {
        final dt = DateTime.parse(completedAt).toLocal();
        timeLabel =
            '${dt.day}/${dt.month} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      } catch (_) {}
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 8, left: 4),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
            decoration: BoxDecoration(
              color: const Color(0xFFD1FAE5),
              borderRadius: BorderRadius.circular(5),
            ),
            child: Text(
              actionType.toUpperCase(),
              style: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: Color(0xFF059669),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  productName,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                ),
                if (notes.isNotEmpty)
                  Text(
                    notes,
                    style: const TextStyle(fontSize: 11, color: Colors.grey),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (photoUrl.isNotEmpty)
                GestureDetector(
                  onTap: () => _showPhoto(context, photoUrl),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Image.network(
                      photoUrl,
                      width: 36,
                      height: 36,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const Icon(
                        Icons.broken_image_outlined,
                        size: 20,
                        color: Colors.grey,
                      ),
                    ),
                  ),
                )
              else
                const Icon(Icons.check_circle, color: Color(0xFF059669), size: 20),
              const SizedBox(height: 2),
              Text(
                timeLabel,
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showPhoto(BuildContext context, String url) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: const Text(
                'Foto evidencia',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
            ),
            Image.network(url, fit: BoxFit.contain),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cerrar'),
            ),
          ],
        ),
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

class _SwipeableActionCard extends StatelessWidget {
  final Map<String, dynamic> action;
  final VoidCallback onComplete;
  final VoidCallback onDonate;

  const _SwipeableActionCard({
    required this.action,
    required this.onComplete,
    required this.onDonate,
  });

  @override
  Widget build(BuildContext context) {
    final actionId = action['id']?.toString() ?? UniqueKey().toString();
    return Dismissible(
      key: ValueKey(actionId),
      // Deslizar derecha → completar
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF059669),
          borderRadius: BorderRadius.circular(14),
        ),
        alignment: Alignment.centerLeft,
        child: const Row(children: [
          Icon(Icons.check_circle_rounded, color: Colors.white, size: 28),
          SizedBox(width: 10),
          Text('Completar', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15)),
        ]),
      ),
      // Deslizar izquierda → donar
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
          HapticFeedback.mediumImpact();
          onComplete();
          return false; // el dialog maneja la lógica real
        } else {
          HapticFeedback.selectionClick();
          onDonate();
          return false;
        }
      },
      child: _ActionCard(action: action, onComplete: onComplete, onDonate: onDonate),
    );
  }
}

class _ActionCard extends StatelessWidget {
  final Map<String, dynamic> action;
  final VoidCallback onComplete;
  final VoidCallback onDonate;

  const _ActionCard({
    required this.action,
    required this.onComplete,
    required this.onDonate,
  });

  @override
  Widget build(BuildContext context) {
    final score = action['priority_score'] as int? ?? 0;
    final actionType = action['action_type'] as String? ?? '';
    final notes = action['notes'] as String? ?? '';
    final batch = action['batches'] as Map<String, dynamic>?;
    final product = batch?['products'] as Map<String, dynamic>?;

    final productName = product?['name'] as String? ?? 'Producto';
    final pasillo = product?['pasillo'] as String? ?? '?';
    final estanteria = product?['estanteria'] as String? ?? '?';
    final nivel = product?['nivel'] as String? ?? '?';
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
                  'Pasillo $pasillo — E$estanteria N$nivel',
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
                  label: const Text('Donar en su lugar'),
                  onPressed: onDonate,
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
