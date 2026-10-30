# Error de precio

Bot gratuito que cada 5 minutos vigila directamente varias tiendas online,
guarda el historial de precios de cada producto y te avisa por Telegram cuando
detecta un posible **error de precio**. No depende de webs de chollos ni de APIs
de pago.

## Tiendas

| Tienda | Qué vigila |
|---|---|
| LDLC | 29 categorías: gráficas, procesadores, SSD, portátiles, consolas, LEGO, audio, TV… |
| GAME | Todas las ofertas (80 páginas), novedades, consolas, videojuegos, PC gaming |
| xtralife | Ofertas, novedades, ofertas Nintendo/PlayStation, consolas |
| Druni | Ofertas flash, novedades, perfumes (mujer, hombre, premium, estuches), lujo |
| Lidl | Portada, ofertas semanales y todas las secciones que aparezcan en la portada |
| IKEA | Bajadas de precio, última oportunidad, precio más bajo |
| Conforama | Ofertas y liquidación |
| Tiendanimal | Ofertas |
| Miravia | Ofertas flash |

Las páginas de ofertas se leen en cada búsqueda. El resto se reparte entre
búsquedas, así que cada categoría se revisa cada 15-60 minutos según la tienda.

No se pueden vigilar Amazon, PcComponentes, MediaMarkt, El Corte Inglés,
Carrefour, Worten, Decathlon, eBay ni Back Market: tienen protección anti-bots y
el bot no se la salta.

## Cuándo avisa

- **Bajada respecto a la media:** un producto con historial cae al menos un
  `DESCUENTO_MIN` % (50 %) por debajo de su precio medio. Es la señal más fiable.
- **Precio tachado:** un producto nuevo, o sin historial que baja de precio, está
  al menos un `DESCUENTO_MIN_TACHADO` % (70 %) por debajo del precio tachado que
  muestra la propia tienda. Es más exigente, porque muchas tiendas inflan el
  precio tachado.
- Solo productos cuyo precio de referencia sea de al menos `PRECIO_MIN` (30 €).
- La primera vez que lee una página solo apunta los precios, sin avisar. Así no
  te llegan todas las rebajas que ya existían. Los avisos empiezan cuando cambia algo.
- Un mismo producto no se repite durante 3 días, salvo que baje otro 5 %.

## Configuración

En **Settings → Secrets and variables → Actions**:

- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Variable `BOT_ACTIVO` = `true` para que busque cada 5 minutos

Ajustes opcionales (pestaña Variables):

| Variable | Por defecto | Qué hace |
|---|---|---|
| `DESCUENTO_MIN` | `50` | % por debajo de la media del historial |
| `DESCUENTO_MIN_TACHADO` | `70` | % por debajo del precio tachado de la tienda |
| `PRECIO_MIN` | `30` | Ignora productos que normalmente valen menos (€) |
| `TIENDAS` | (todas) | Solo estas, separadas por comas: `LDLC,GAME,Druni` |
| `MAX_AVISOS` | `15` | Mensajes con foto por búsqueda (el resto llega en un resumen) |

El historial se guarda en la caché de GitHub Actions entre ejecuciones.

## Probarlo en local

Solo necesita Python 3.10 o superior, sin dependencias:

```sh
python3 bot.py --simular                 # enseña qué avisaría, sin mandar ni guardar nada
python3 bot.py --simular --tienda GAME   # solo una tienda
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python3 bot.py --prueba                  # comprueba que llegan los mensajes
python3 bot.py --bucle 300               # busca cada 5 minutos sin parar
python3 -m unittest discover -s tests    # tests
```

## Añadir una tienda

Crea `tiendas/<tienda>.py` con `NOMBRE`, `FIJAS`, `ROTAR`, `POR_EJECUCION` y
`leer(html)` (devuelve una lista de `Producto`), y añádelo a `tiendas/__init__.py`.
