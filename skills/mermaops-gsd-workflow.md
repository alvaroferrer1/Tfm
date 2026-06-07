# skill: mermaops-gsd-workflow
Objetivo: Disciplina de trabajo. Evitar que el agente actúe sin pensar.
Cuándo: Siempre. Especialmente antes de cambios grandes.
Fusiona: audit-real + token-saving + fix-p0.

Protocolo:
1. Audita primero. Lee PROJECT_STATE.md y BUG_BACKLOG.md.
2. Identifica el P0 o tarea concreta. No hagas lo que te apetezca.
3. Lee SOLO los archivos del problema. No el proyecto entero.
4. Planifica antes de codificar. Explica el plan.
5. Cambios pequeños. Un archivo a la vez si es posible.
6. Prueba. Ejecuta comando de verificación.
7. Resume: archivos tocados, qué cambió, cómo probarlo.

Ahorro de tokens:
- Lee solo lo necesario.
- No pegues archivos completos en respuesta.
- No expliques teoría si el usuario pide arreglar.
- Máximo 1 sesión por bloque de funcionalidad.

Checklist antes de decir "listo":
- ¿Tests siguen pasando? (python -m pytest backend/tests/ -q)
- ¿flutter analyze sin errores?
- ¿No hay credenciales en el código?
- ¿El archivo modificado existe y compila?
