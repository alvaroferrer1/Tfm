# skill: mermaops-json-contracts
Objetivo: Payloads limpios entre agentes, backend y Flutter.
Cuándo: Al cambiar endpoints, modelos Pydantic, o cuando Flutter crashea con JSON.

Regla 1: Agentes no se pasan textos largos entre sí.
Regla 2: Cada agente escribe resultado estructurado en BD.
Regla 3: Flutter espera tipos exactos — nunca devolver null donde se espera int/double.

Contratos endpoint → Flutter (tipos que Flutter espera):
- priority_score: int (0-100)
- value_at_risk: double
- expiry_date: String "YYYY-MM-DD"
- quantity: int
- avg_merma_pct: double
- risk: String ("ALTO"|"MEDIO"|"BAJO")
- status: String ("pending"|"completed"|"cancelled")

Contratos estado agentes (agent_runs tabla):
- run_id: uuid
- store_id: String
- agent_type: String
- trigger_source: String
- tools_used: List[String]
- duration_ms: int
- result_summary: String (max 500 chars)

Checklist al cambiar endpoint:
- [ ] ¿Pydantic BaseModel valida el input?
- [ ] ¿La respuesta JSON tiene los mismos campos que espera Flutter?
- [ ] ¿Los campos opcionales tienen valores por defecto, no null inesperado?
- [ ] ¿Los tipos numéricos son consistentes (no mezclar int y str para el mismo campo)?
- [ ] ¿flutter analyze no da errores de tipo tras el cambio?
