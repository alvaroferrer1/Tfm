# skill: mermaops-flutter-ux-design
Objetivo: UI consistente, sin errores visuales, que impresione en la defensa.
Cuándo: Al tocar cualquier pantalla Flutter, colores, layout o navegación.

Paleta oficial:
- Primary: Color(0xFF6C3FC5) — violeta MermaOps
- Success: Colors.green.shade600
- Warning: Colors.amber.shade700
- Danger: Colors.red.shade700
- Surface: Colors.white / Colors.grey.shade50
- Text secondary: Colors.grey.shade600

Pantallas activas (verificado en router.dart):
- /dashboard → DashboardScreen (home)
- /products → ProductsScreen
- /actions → ActionsScreen
- /reports → ReportsScreen
- /agents → AgentsScreen (6º nav item, icono psychology)
- /chat → ChatScreen (Chuwi app)

Reglas de layout:
- Padding estándar: 16px horizontal, 12px vertical
- Cards: BorderRadius.circular(12), elevation 0 con border sutil
- Bottom nav: 6 items max — no añadir más sin quitar uno
- Listas largas: ListView.builder, nunca Column con expand

Errores frecuentes que rompen la demo:
- OverflowError: Wrap Row en Flexible o usar Expanded
- RenderFlex: no usar Column sin Expanded dentro de Column sin alto fijo
- "null check": verificar que el provider devuelve datos antes de hacer .length

Checklist al añadir pantalla:
- [ ] Registrada en router.dart con GoRoute
- [ ] Añadida a shell_scaffold.dart si va en nav bar
- [ ] Responsive: prueba con ventana estrecha (400px)
- [ ] Estado vacío: mostrar widget, no pantalla en blanco
- [ ] Estado error: mostrar mensaje, no excepción sin capturar

Patrones de estado en Riverpod:
```dart
final provider = FutureProvider<T>((ref) async { ... });
// En build():
final state = ref.watch(provider);
return state.when(
  data: (d) => ...,
  loading: () => const Center(child: CircularProgressIndicator()),
  error: (e, _) => Center(child: Text('Error: $e')),
);
```
