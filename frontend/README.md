# Frontend (Vue 3 + Vite)

SPA served at `/` by the FastAPI app (build output: `frontend/dist`). Legacy `/app/*` URLs redirect to `/*`.

```bash
npm ci
npm run dev          # http://127.0.0.1:5173 (API proxied to :8002)
npm run build
npm run test:run
npm run gen-locales  # refresh types/format of src/i18n/generated
npm run compare-layout  # optional Playwright screenshots (not CI)
```
