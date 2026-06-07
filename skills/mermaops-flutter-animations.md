# skill: mermaops-flutter-animations
Objetivo: Animaciones que demuestran calidad técnica sin coste de rendimiento.
Cuándo: Al añadir barras de progreso, transiciones, indicadores de cambio.

Animaciones ya implementadas (no reimplementar):
- TweenAnimationBuilder en _SupplierCard: barra de merma animada al expandir
- AnimatedContainer en _TodayProgressCard: barra de progreso completadas/total
- CircularProgressIndicator en estados loading de todos los providers

Patrón estándar TweenAnimationBuilder (para barras):
```dart
TweenAnimationBuilder<double>(
  tween: Tween(begin: 0.0, end: valor),
  duration: const Duration(milliseconds: 800),
  curve: Curves.easeOut,
  builder: (_, v, __) => LinearProgressIndicator(value: v, ...),
)
```

Cuándo usar cada tipo:
- Datos que llegan del server → TweenAnimationBuilder (comienza en 0, anima hasta valor)
- Aparición de cards → AnimatedOpacity + SlideTransition con delay escalonado
- Estado cambia (pendiente→completado) → AnimatedContainer con color
- Listas → no animar (coste alto, poco valor visual)

Reglas de rendimiento:
- Duración máxima útil: 600ms. Más de 1s parece lento en demo.
- Curve preferida: Curves.easeOut (natural) o Curves.elasticOut (para números)
- NO animar en ListView items — solo en cards fijas de la pantalla
- Usar const donde sea posible dentro del builder

Lo que el tribunal verá (y que impresiona):
1. Dashboard: barra de progreso de acciones completadas se llena al cargar
2. Informes: barra de merma de proveedor se anima al expandir la card
3. Acciones: badge de prioridad con color (ya existe, sin animación — ok)

Checklist antes de añadir animación:
- [ ] ¿Aporta información (no es solo decorativa)?
- [ ] ¿Dura ≤600ms?
- [ ] ¿No está en un item de lista larga?
- [ ] ¿Tiene fallback si el valor es null?
