// Vitest: as línguas são chunks carregados a pedido (i18n/index.ts). Nos testes ficam todas
// carregadas antes de cada ficheiro, como se o main.ts já as tivesse descarregado.
import { LANG_CODES, loadLang } from '@/i18n'

await Promise.all(LANG_CODES.map(loadLang))
