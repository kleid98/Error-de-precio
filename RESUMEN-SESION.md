# Resumen de sesión — bot de errores de precio

> **Qué es este archivo:** un resumen del estado del proyecto para que una sesión
> nueva de Claude Code pueda continuar sin haber visto la conversación anterior.
> Se sobrescribe en cada limpieza. Generado el **30-10-2026** (≈ 00:45 UTC).

## 1. Qué es y en qué punto está

Bot gratuito en Python (solo librería estándar) que vigila tiendas online
directamente, guarda el historial de precios de cada producto y avisa por
Telegram cuando un producto cae **≥ 50 % por debajo de su precio medio de los
últimos 99 días**. Ale lo quiere para **arbitraje**: comprar errores de precio y
revenderlos (Wallapop, Vinted, eBay). Corre en **GitHub Actions** cada 5 minutos.

**Estado:** el código está terminado, subido a `main` y probado. Las búsquedas
lanzadas a mano en Actions (ejecuciones #1 a #3) terminan bien y leen las 6
tiendas (~1.500 productos por búsqueda). **Falta confirmar que el cron se ejecuta
solo**: hasta las 00:40 UTC del 30-10 no había aparecido ninguna ejecución con
`event=schedule`. El historial empezó a llenarse el 30-10 a las 00:36 UTC, así que
los primeros avisos reales no pueden llegar antes de que pasen 24 h.

## 2. Decisiones clave y por qué

- **Nada de pago.** Se descartó la API de Keepa (≈ 49 €/mes) porque Ale no quiere pagar.
- **Nada de Chollometro.** Se usó en una primera versión, pero Ale lo rechazó: si
  algo ya está publicado allí, llegamos tarde. Ahora el bot lee las tiendas directamente.
- **No se saltan protecciones anti-bots.** Amazon, PcComponentes, MediaMarkt,
  El Corte Inglés, Carrefour, Worten, Decathlon, la web de eBay, Back Market y
  CamelCamelCamel devuelven 403/503 o un reto de Cloudflare. Se intentó probar un
  navegador headless para pasar Cloudflare y el sistema lo **denegó por "Bot Check
  Circumvention"**. No volver a intentarlo.
- **Solo la media de 99 días cuenta.** El precio tachado de la tienda **no** se usa
  para avisar; lo pidió Ale de forma explícita. Hubo una versión que avisaba con
  el precio tachado y se quitó.
- **Se evitan los productos poco revendibles** (petición de Ale): ropa, muebles y
  voluminosos, reacondicionados o usados, y productos con media < 30 €. Por eso se
  quitaron **IKEA, Conforama** (muebles) y **Miravia** (productos genéricos;
  además devolvía 0 productos desde los servidores de GitHub).
- **Pausa nocturna de 1:00 a 9:00 (hora de Madrid)**, porque Ale duerme a esas horas.
- **Repositorio público** para que GitHub Actions sea gratis e ilimitado. En
  privado, cada 5 min agotaría los 2.000 min/mes gratis.
- **Avisos por Telegram** con foto, precio actual, precio anterior, media, días de
  historial, ahorro y enlace.

## 3. Qué se ha creado

Repositorio: **github.com/kleid98/Error-de-precio** (público, rama `main`).

| Ruta | Qué es |
|---|---|
| `bot.py` | Núcleo: lectura en paralelo, historial, detección, filtro de tipos, pausa nocturna, Telegram, CLI |
| `tiendas/base.py` | `Producto` (dataclass), `numero()`, `limpiar()`, `objetos_json()`, `productos_jsonld()` |
| `tiendas/ldlc.py` | LDLC: JSON-LD de 29 categorías, `/paginaN/`, 48 productos por página |
| `tiendas/game.py` | GAME: datos RSC de Next.js (`self.__next_f.push`), `/ofertas?pagina=N` (80 págs.), consolas, etc. |
| `tiendas/xtralife.py` | xtralife: HTML de `<poster-thumbnail>`, `/ofertas-rebajas` y otras 5 páginas |
| `tiendas/druni.py` | Druni (Magento): categorías hoja `?p=N`, `data-price-type="finalPrice"` |
| `tiendas/lidl.py` | Lidl: JSON en `data-grid-data`; descubre secciones `/c/<slug>/a<id>` desde la portada |
| `tiendas/tiendanimal.py` | Tiendanimal (Salesforce): `/ofertas/?start=N&sz=24` |
| `tiendas/__init__.py` | `TODAS = [ldlc, game, xtralife, druni, lidl, tiendanimal]` |
| `tests/test_bot.py` | 19 tests (media, detección, exclusiones, pausa, rotación, flujo completo) |
| `.github/workflows/buscar.yml` | Cron `*/5 7-23 * * *` (UTC) + `workflow_dispatch`; caché `historial99-` |
| `README.md` | Documentación de uso y variables |
| `.gitignore` | Ignora `estado/` y `__pycache__/` |

**Cómo funciona por dentro:**
- Cada tienda tiene páginas `FIJAS` (se leen en todas las búsquedas) y `ROTAR`
  (se leen `POR_EJECUCION` cada vez; el cursor se guarda en el estado).
- **Estado:** `estado/historial99.json`, que se conserva entre ejecuciones con
  `actions/cache` (clave `historial99-<run_id>`). Por producto guarda
  `h` = lista de cambios `[momento, precio]`, `u` = último precio, `p0` = primera
  vez visto, `t` = última vez visto, y `av`/`at` = precio y momento del último aviso.
- **Media:** ponderada por el tiempo que estuvo a cada precio, sobre los últimos
  99 días (`media_periodo`).
- **Reglas de aviso** (`evaluar`), todas a la vez:
  - al menos `HORAS_MIN_HISTORIAL` (24 h) de historial;
  - el precio ha bajado al menos un 3 % desde la lectura anterior;
  - precio ≤ media × (1 − 50 %);
  - media ≥ 30 €.
- No repite el aviso de un producto en 72 h salvo que baje otro 5 %. Envía 15
  avisos con foto como máximo; el resto llega en un mensaje de resumen.
- **Exclusiones:** lista de regex `EXCLUIDOS` en `bot.py`, comparada sin tildes;
  se pueden añadir palabras con la variable `EXCLUIR`.

**CLI:**
- `python3 bot.py`: una búsqueda.
- `--simular`: busca sin enviar ni guardar nada.
- `--tienda X`: solo esa tienda.
- `--prueba`: manda un mensaje de prueba a Telegram.
- `--bucle 300`: busca cada 5 minutos sin parar.
- `--sin-pausa`: busca aunque sea la pausa nocturna.
- Tests: `python3 -m unittest discover -s tests`.

## 4. Configuración y credenciales (solo dónde están)

- **Secrets de GitHub Actions** (Settings → Secrets and variables → Actions):
  - `TELEGRAM_BOT_TOKEN`: token del bot de Telegram **@MeLoQuitanDeLasManos_bot**;
  - `TELEGRAM_CHAT_ID`: chat ID de Ale.

  Ale dijo que los había creado, y la ejecución #1 lo confirmó: llegaron mensajes.
- **Variable `BOT_ACTIVO=true`** (pestaña Variables): activa el cron. **Sin
  confirmar** si Ale la creó. Sin ella, las ejecuciones programadas aparecen con
  el job omitido (*skipped*).
- **Variables opcionales** (no creadas):
  - `DESCUENTO_MIN` (50) y `PRECIO_MIN` (30);
  - `HORAS_MIN_HISTORIAL` (24);
  - `EXCLUIR` y `TIENDAS`;
  - `MAX_AVISOS` (15);
  - `PAUSA_NOCHE` (`1-9`, o `no`) y `ZONA_HORARIA` (`Europe/Madrid`).
- Para pruebas locales con Telegram hay que exportar `TELEGRAM_BOT_TOKEN` y
  `TELEGRAM_CHAT_ID` en el entorno. **No** están en ningún archivo del repositorio.

## 5. Pendiente / próximos pasos

1. **Comprobar que el cron se ejecuta solo** a partir de las 08:00 UTC (9:00 en
   Madrid). Con la herramienta MCP de GitHub: `actions_list` →
   `list_workflow_runs` y buscar `event: schedule`.
   - **Ejecuciones con el job omitido:** falta `BOT_ACTIVO`. Pasar a Ale el enlace
     https://github.com/kleid98/Error-de-precio/settings/variables/actions/new
   - **No hay ninguna:** GitHub aún no ha activado el cron; seguir esperando.
   - **Las de 07:xx UTC:** en invierno deben imprimir "Pausa nocturna".

   Había un recordatorio programado para esto (`trig_011BYJRRr2aUJ6QwmsZUe9wn`, a
   las 08:20 UTC), pero salta en la sesión **antigua**. La sesión nueva debe hacer
   la comprobación ella misma.
2. Revisar los **primeros avisos reales** (a partir del 31-10) y ajustar filtros o
   umbrales si llegan falsos positivos o productos no revendibles.
3. **eBay y AliExpress** quedaron pendientes. Tienen API oficial gratuita, pero Ale
   tiene que darse de alta como desarrollador y conseguir claves. No hay código
   para ellas.
4. Ideas no pedidas y aún no hechas:
   - estimar el precio de reventa de segunda mano;
   - lista blanca de marcas;
   - detectar productos "sin marca", que ahora no se filtran porque no hay forma
     fiable de hacerlo por el título.

## 6. Cosas a tener en cuenta

- **Cron de GitHub:** va en UTC, puede retrasarse 10-15 minutos y en
  repositorios nuevos puede tardar en arrancar. La franja `7-23` UTC cubre de 9:00
  a 1:00 en Madrid tanto en invierno como en verano; la hora exacta la filtra
  `Config.en_pausa()` con `zoneinfo`.
- **Caché de Actions:** si el bot deja de ejecutarse más de 7 días, GitHub borra
  la caché y **se pierde el historial**.
- **Restricciones de `robots.txt` que se respetan:**
  - LDLC: `/es-es/oportunidades/` y `/buscar/` prohibidos.
  - Lidl: `?offset=`, `sort=` e `id=` prohibidos, así que solo se lee la primera
    página de cada sección.
  - Miravia: prohíbe `page=`.
  - xtralife: `Crawl-delay: 20` solo para bots concretos, no para `*`.
- **Páginas que no sirven:** las `/seleccion/...` de xtralife se generan en el
  navegador y devuelven 0 productos. `/perfumes` de Druni es una portada con solo 4
  productos; hay que usar las categorías hoja.
- **Errores de red:** pueden cortar la respuesta (`IncompleteRead`); `pedir()` los
  convierte en `RuntimeError` y la tienda sigue con la página siguiente.
- **El token de Telegram** se pegó en el chat de la sesión anterior. Si a Ale le
  preocupa, puede regenerarlo en @BotFather (`/revoke`) y actualizar el secret.
- **Exclusiones agresivas:** el filtro descarta, por ejemplo, un "Funko + Camiseta"
  de xtralife por la palabra "camiseta". `\bmesa\b` no está excluida a propósito,
  para que pasen los juegos de mesa.
- Al probar en local, usar `ARCHIVO_ESTADO` apuntando a un archivo temporal para
  no mezclarlo con el estado real.
- No poner identificadores de modelo en commits ni en el código.

## 7. Preferencias de trabajo de Ale

- Habla en **español** y trabaja **desde el móvil**: dale enlaces directos a las
  páginas de ajustes de GitHub y pasos cortos. Los secretos de GitHub hay que
  crearlos desde el navegador del móvil, porque la app de GitHub no lo permite.
- **No quiere pagar** por servicios ni APIs.
- Rechazó una vez el cuadro de preguntas interactivo: mejor preguntar en texto
  normal y dar una recomendación.
- Cree que el bot "gasta tokens". Ya se le explicó que no gasta tokens de IA ni
  dinero.
- Se le pueden hacer push directos a `main`; es el flujo que se ha seguido toda la
  sesión.
