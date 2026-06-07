# skill: fix-p0
Objetivo: Arreglar un P0 del BUG_BACKLOG.md sin romper nada.
Cuándo: Cuando hay un P0 activo y el usuario pide arreglarlo.
Checklist:
1. Leer solo BUG_BACKLOG.md + archivos del P0 específico
2. Localizar línea exacta del fallo
3. Implementar fix mínimo (no refactorizar)
4. Verificar con prueba concreta (comando, grep, test)
5. Actualizar BUG_BACKLOG.md (marcar resuelto), CHANGELOG.md, PROJECT_STATE.md
- NO tocar archivos no relacionados
- NO añadir dependencias
- NO cambiar arquitectura
Output: Qué cambió, dónde, prueba real de que funciona.
