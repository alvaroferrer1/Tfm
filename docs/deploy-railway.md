# Deploy MermaOps en Railway — 24/7 autónomo

> Objetivo: que el tribunal vea datos reales de días anteriores y el scheduler funcionando solo.
> Tiempo: ~20 minutos la primera vez.

---

## Paso 1 — Cuenta Railway

1. Ve a [railway.app](https://railway.app) → Sign in with GitHub
2. New Project → Deploy from GitHub repo → selecciona `tfm-final-master`

## Paso 2 — Variables de entorno en Railway

En el proyecto → Settings → Variables → añade exactamente estas:

```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://bf....supabase.co
SUPABASE_KEY=sb_secret_...
SUPABASE_SERVICE_KEY=sb_secret_...
TELEGRAM_BOT_TOKEN=853...
STORE_ID=demo-store-001
APP_PORT=8001
```

> Cópialas de tu `.env` local.

## Paso 3 — Deploy

Railway detecta el `Dockerfile` automáticamente. Click **Deploy**.

Tarda ~3 minutos. Cuando diga "Active", tu backend está en:
```
https://tu-proyecto.railway.app
```

## Paso 4 — Verificar

```bash
curl https://tu-proyecto.railway.app/health
# {"status":"ok","store_id":"demo-store-001",...}
```

## Paso 5 — Conectar la app Flutter al servidor

```bash
# Para la demo en Chrome apuntando al servidor de Railway:
flutter run -d chrome --dart-define=API_URL=https://tu-proyecto.railway.app/api/v1
```

O actualiza el defaultValue en `app/lib/core/api_service.dart`:
```dart
defaultValue: 'https://tu-proyecto.railway.app/api/v1',
```

## Qué consigue esto para el tribunal

- El scheduler corre solo a las 07:30 → genera briefs aunque tu PC esté apagado
- Los datos en Supabase se acumulan días antes de la defensa
- Respuesta: "Lleva X días funcionando en producción en Railway"
- Coste: **$0** (Railway tiene free tier para proyectos de hobby)

## Si Telegram da conflicto 409

Railway y tu backend local no pueden hacer polling al mismo tiempo.
Soluciones:
1. Para tu backend local (`Ctrl+C`) cuando Railway esté activo
2. O usa webhook en Railway (más avanzado, no necesario para el TFM)
