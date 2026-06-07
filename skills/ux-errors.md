# skill: ux-errors
Objetivo: Eliminar errores técnicos visibles al usuario final.
Cuándo: Al revisar app Flutter o mensajes Telegram de error.
Checklist:
- Buscar: detail=str(e), throw Exception('...'), errorCode.name
- Cada error HTTP 5xx → el usuario ve mensaje genérico en español
- Cada estado vacío tiene placeholder útil (no "[]" ni "null")
- Loading states: spinner visible, no pantalla en blanco
- Errores de red: mensaje "Sin conexión" + botón reintentar
- En Telegram: nunca mostrar traceback ni nombre de fichero Python
Output: Lista de errores encontrados con archivo:línea + fix aplicado.
