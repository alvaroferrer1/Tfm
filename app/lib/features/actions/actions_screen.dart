import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_service.dart';
import '../../core/supabase_client.dart';
import '../../core/theme.dart';
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
          _PendingTab(onComplete: _showCompleteDialog),
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
                    color: result!.startsWith('Error')
                        ? const Color(0xFFFEE2E2)
                        : const Color(0xFFD1FAE5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    result!,
                    style: TextStyle(
                      fontSize: 12,
                      color: result!.startsWith('Error')
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
                                loading = false;
                              });
                              if (imp > 0) {
                                ref.invalidate(pendingActionsProvider);
                              }
                            } catch (e) {
                              setModalState(() {
                                result = 'Error: $e';
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
                          child: Image.file(
                            File(photoFile!.path),
                            width: 40,
                            height: 40,
                            fit: BoxFit.cover,
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
        builder: (ctx, setModalState) => Padding(
          padding: EdgeInsets.fromLTRB(
            16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 16,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFD1FAE5),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.volunteer_activism,
                        color: Color(0xFF059669), size: 20),
                  ),
                  const SizedBox(width: 10),
                  const Text(
                    'Registrar donación',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                productName,
                style: const TextStyle(fontSize: 13, color: Colors.grey),
              ),
              const SizedBox(height: 16),
              const Text(
                'Banco de alimentos',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 6),
              ...entities.map((e) => RadioListTile<String>(
                    value: e,
                    groupValue: selectedEntity,
                    title: Text(e, style: const TextStyle(fontSize: 13)),
                    contentPadding: EdgeInsets.zero,
                    visualDensity: VisualDensity.compact,
                    activeColor: const Color(0xFF059669),
                    onChanged: (v) => setModalState(() => selectedEntity = v!),
                  )),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: qtyCtrl,
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        labelText: 'Unidades (máx. $maxQty)',
                        suffixText: 'uds',
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: notesCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Notas (opcional)',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                icon: const Icon(Icons.favorite_outline, size: 18),
                label: const Text('Confirmar donación'),
                onPressed: () async {
                  Navigator.pop(context);
                  final qty = int.tryParse(qtyCtrl.text) ?? maxQty;
                  await _completeDonation(
                    ref,
                    action,
                    entity: selectedEntity,
                    quantity: qty,
                    notes: notesCtrl.text,
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF059669),
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        ),
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
      // Mark action completed — completed_by stores email for legible historial
      await supabase.from('actions').update({
        'status': 'completed',
        'completed_by': userLabel,
        'completed_at': DateTime.now().toIso8601String(),
        'notes': notes.isEmpty ? 'Donado a $entity — $quantity uds' : notes,
        'donation_entity': entity,
        'donation_quantity': quantity,
      }).eq('id', actionId);

      // Register in donations table
      await supabase.from('donations').insert({
        'store_id': storeId,
        'batch_id': action['batch_id'],
        'action_id': actionId,
        'entity': entity,
        'quantity': quantity,
        'product_name': productName,
        'value_donated': (price * quantity),
        'donated_by': userLabel,
        'notes': notes,
      });
    } catch (_) {
      await api.completeAction(
        actionId: actionId,
        completedBy: userLabel,
        notes: 'Donado a $entity — $quantity uds',
      );
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
      } catch (_) {
        // Upload failed — proceed without photo
      }
    }

    try {
      await supabase.from('actions').update({
        'status': 'completed',
        'completed_by': userId,
        'completed_at': DateTime.now().toIso8601String(),
        'notes': notes,
        if (photoUrl.isNotEmpty) 'photo_url': photoUrl,
      }).eq('id', actionId);
    } catch (e) {
      await api.completeAction(
        actionId: actionId,
        completedBy: userId,
        notes: notes,
        photoUrl: photoUrl,
      );
    }
    ref.invalidate(pendingActionsProvider);
  }
}

class _PendingTab extends ConsumerWidget {
  final void Function(BuildContext, WidgetRef, Map<String, dynamic>) onComplete;

  const _PendingTab({required this.onComplete});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final actionsAsync = ref.watch(pendingActionsProvider);
    return actionsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
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
              ...critical.map((a) => _ActionCard(
                    action: a,
                    onComplete: () => onComplete(context, ref, a),
                  )),
              const SizedBox(height: 16),
            ],
            if (others.isNotEmpty) ...[
              _SectionHeader(label: 'OTRAS (${others.length})'),
              ...others.map((a) => _ActionCard(
                    action: a,
                    onComplete: () => onComplete(context, ref, a),
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
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
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

class _ActionCard extends StatelessWidget {
  final Map<String, dynamic> action;
  final VoidCallback onComplete;

  const _ActionCard({required this.action, required this.onComplete});

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
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                icon: const Icon(Icons.check, size: 16),
                label: const Text('Marcar completada'),
                onPressed: onComplete,
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF059669),
                  side: const BorderSide(color: Color(0xFF059669)),
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
    final expiryDate = batch?['expiry_date'] as String? ?? '';

    // Prefer stored pct, then parse from notes, then default 30%
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
        discountPct: discountPct,
        expiryDate: expiryDate,
      ),
    );
  }
}

class _DiscountLabelSheet extends StatelessWidget {
  final String productName;
  final double originalPrice;
  final double newPrice;
  final int discountPct;
  final String expiryDate;

  const _DiscountLabelSheet({
    required this.productName,
    required this.originalPrice,
    required this.newPrice,
    required this.discountPct,
    required this.expiryDate,
  });

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
            // Label preview card
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
                  // Discount badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEF4444),
                      borderRadius: BorderRadius.circular(30),
                    ),
                    child: Text(
                      '-$discountPct%',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    productName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 14),
                  // Prices
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (originalPrice > 0) ...[
                        Text(
                          '${originalPrice.toStringAsFixed(2)} €',
                          style: const TextStyle(
                            fontSize: 16,
                            color: Colors.grey,
                            decoration: TextDecoration.lineThrough,
                          ),
                        ),
                        const SizedBox(width: 12),
                      ],
                      Text(
                        '${newPrice.toStringAsFixed(2)} €',
                        style: const TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.w900,
                          color: Color(0xFFEF4444),
                          letterSpacing: -1,
                        ),
                      ),
                    ],
                  ),
                  if (expiryDate.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEE2E2),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        'Caduca: $expiryDate',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF991B1B),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  const Text(
                    'Precio especial por proximidad a caducidad',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Cerrar'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.print_outlined, size: 18),
                    label: const Text('Imprimir'),
                    onPressed: () {
                      Navigator.pop(context);
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Etiqueta enviada a impresora'),
                          backgroundColor: Color(0xFF059669),
                        ),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFF59E0B),
                      foregroundColor: Colors.white,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
