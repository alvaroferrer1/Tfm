import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_service.dart';
import 'theme.dart' show ShimmerList;

enum UserRole { staff, manager, admin }

extension UserRoleX on UserRole {
  String get label => switch (this) {
        UserRole.staff => 'Empleado',       // empleado de tienda
        UserRole.manager => 'Encargado',    // responsable / manager
        UserRole.admin => 'Admin',
      };

  String get description => switch (this) {
        UserRole.staff => 'Acceso a operaciones del día (escanear, completar acciones)',
        UserRole.manager => 'Acceso completo: informes, agentes, pedidos, ESG',
        UserRole.admin => 'Acceso total incluyendo demo y configuración',
      };

  IconData get icon => switch (this) {
        UserRole.staff => Icons.store_outlined,
        UserRole.manager => Icons.manage_accounts_outlined,
        UserRole.admin => Icons.admin_panel_settings_outlined,
      };

  Color get color => switch (this) {
        UserRole.staff => const Color(0xFF059669),
        UserRole.manager => const Color(0xFF2563EB),
        UserRole.admin => const Color(0xFF7C3AED),
      };

  bool get canViewReports => index >= UserRole.manager.index;
  bool get canViewAgents => index >= UserRole.manager.index;
  bool get canViewDemo => index >= UserRole.admin.index;
}

UserRole _parseRole(String? raw) => switch (raw) {
      'admin' => UserRole.admin,
      'manager' => UserRole.manager,
      _ => UserRole.staff,
    };

final userRoleProvider = FutureProvider<UserRole>((ref) async {
  try {
    final profile = await api.getCurrentUser();
    return _parseRole(profile['role'] as String?);
  } catch (_) {
    return UserRole.staff;
  }
});

/// Wrapper que muestra el child si el usuario tiene el rol requerido,
/// o una pantalla de acceso restringido si no lo tiene.
class RoleGate extends ConsumerWidget {
  final UserRole requiredRole;
  final Widget child;

  const RoleGate({
    super.key,
    required this.requiredRole,
    required this.child,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final roleAsync = ref.watch(userRoleProvider);

    return roleAsync.when(
      loading: () => const ShimmerList(count: 2, itemHeight: 60),
      error: (_, __) => child,
      data: (role) {
        if (role.index >= requiredRole.index) return child;
        return _AccessDenied(required: requiredRole, current: role);
      },
    );
  }
}

class _AccessDenied extends StatelessWidget {
  final UserRole required;
  final UserRole current;

  const _AccessDenied({required this.required, required this.current});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 88,
              height: 88,
              decoration: BoxDecoration(
                color: const Color(0xFFFEF3C7),
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0xFFF59E0B), width: 2),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFF59E0B).withValues(alpha: 0.15),
                    blurRadius: 20,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child:
                  const Icon(Icons.lock_outline, size: 38, color: Color(0xFFD97706)),
            ),
            const SizedBox(height: 24),
            const Text(
              'Acceso restringido',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: Color(0xFF1F2937),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Esta sección requiere nivel ${required.label}.\nTu perfil actual: ${current.label}.',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, color: Color(0xFF6B7280), height: 1.5),
            ),
            const SizedBox(height: 28),
            // Role comparison chips
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _RoleChip(role: current, label: 'Tu rol'),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 10),
                  child: Icon(Icons.arrow_forward, size: 16, color: Color(0xFFD1D5DB)),
                ),
                _RoleChip(role: required, label: 'Requerido', locked: true),
              ],
            ),
            const SizedBox(height: 28),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFE5E7EB)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.info_outline, color: Color(0xFF3B82F6), size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Contacta con tu ${required.label.toLowerCase()} '
                      'para obtener acceso a esta sección.',
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF374151),
                        height: 1.4,
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

class _RoleChip extends StatelessWidget {
  final UserRole role;
  final String label;
  final bool locked;

  const _RoleChip({required this.role, required this.label, this.locked = false});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: role.color.withValues(alpha: locked ? 0.08 : 0.1),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: role.color.withValues(alpha: locked ? 0.3 : 0.5),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (locked) ...[
                Icon(Icons.lock, size: 12, color: role.color),
                const SizedBox(width: 4),
              ],
              Text(
                role.label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: role.color,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF)),
        ),
      ],
    );
  }
}
