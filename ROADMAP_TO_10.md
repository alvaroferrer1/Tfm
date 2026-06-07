# ROADMAP_TO_10.md — Plan para matrícula MermaOps
> Actualizado: 2026-05-25

## Nota actual estimada: 8.5 / 10

### Por qué no es 10 ahora mismo
1. Demo endpoints sin auth (P0 seguridad — nota baja en revisión)
2. Errores internos visibles al cliente en 25+ endpoints
3. App chat no muestra razonamiento real de Kuine (chips de tools vacíos)
4. store_comparison vacío → una tab del dashboard aparece rota
5. Flujo de login sin feedback de error → mala UX para demo
6. Telegram advance sin confirmación → peligroso en demo en vivo

---

## Para demo estable (8/10 garantizado)
- [ ] P0-001: Auth en demo endpoints (2h)
- [ ] P0-002: Sanitizar detail=str en routes_demo + routes.py (1h)
- [ ] P1-002: Datos store_comparison en seed (30min)
- [ ] P1-005: Invalidar providers tras advance en app (30min)

## Para sobresaliente (9/10)
- [ ] P1-003: Chat muestra tools usadas en Flutter (2h)
- [ ] P1-004: Login con mensaje de error claro (1h)
- [ ] Telegram /demo pide confirmación antes de advance grande (1h)
- [ ] Scheduler: log visible de alertas proactivas enviadas
- [ ] Brief en app: ver el brief del día al abrir (no solo en reports)

## Para producto real potente (10/10 — matrícula)
- [ ] Streaming real en app chat (SSE o WebSocket)
- [ ] Push notifications en Flutter cuando hay nuevos críticos
- [ ] Modo offline básico (caché local de acciones pendientes)
- [ ] Onboarding: primera vez que abre la app, explica qué es cada pantalla
- [ ] Multi-tienda real: el dueño ve N tiendas, el encargado solo la suya
- [ ] Historia de decisiones de Kuine: "esta semana decidí donar X veces vs rebajar"

## Qué NO hacer esta semana (no merece la pena)
- NO refactorizar arquitectura de agentes — funciona bien
- NO cambiar stack de BD — Supabase está funcionando
- NO añadir nuevos agentes — los 11 actuales cubren todo
- NO migrar a WebSockets para chat — el polling es suficiente para TFM
- NO multi-idioma — solo español en TFM
- NO CI/CD complejo — make test es suficiente

## Orden de ataque recomendado
1. BUG-P0-001 + P0-002 (seguridad, 2h) → demo segura
2. BUG-P1-002 store_comparison (30min) → dashboard sin huecos
3. BUG-P1-005 invalidar providers (30min) → demo en vivo fluida
4. BUG-P1-004 login feedback (1h) → UX limpia
5. BUG-P1-003 tools en chat (2h) → demuestra razonamiento IA
