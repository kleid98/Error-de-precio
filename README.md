# Error de precio

Bot gratuito que cada 5 minutos vigila directamente varias tiendas online,
guarda el historial de precios de cada producto y te avisa por Telegram cuando
un producto cae **al menos un 50 % por debajo de su precio medio de los últimos
99 días**. El precio tachado que muestra la tienda no cuenta: solo el historial
que recoge el propio bot.

## Tiendas

| Tienda | Qué vigila |
|---|---|
| LDLC | 29 categorías: gráficas, procesadores, SSD, portátiles, consolas, LEGO, audio, TV… |
| GAME | Todas las ofertas (80 páginas), novedades, consolas, videojuegos, PC gaming |
| xtralife | Ofertas, novedades, ofertas Nintendo/PlayStation, consolas |
| Druni | Ofertas flash, novedades, perfumes (mujer, hombre, premium, estuches), lujo |
| Lidl | Portada, ofertas semanales y todas las secciones que aparezcan en la portada |
| Tiendanimal | Ofertas |

Las páginas de ofertas se leen en cada búsqueda. El resto se reparte entre
búsquedas, así que cada categoría se revisa cada 15-60 minutos según la tienda.

No se vigilan Amazon, PcComponentes, MediaMarkt, El Corte Inglés, Carrefour,
Worten, Decathlon, eBay ni Back Market: tienen protección anti-bots y el bot no se
la salta. IKEA, Conforama y Miravia se han quitado porque venden sobre todo
muebles voluminosos o productos genéricos, que no compensa revender.

## Cuándo avisa

- El producto acaba de bajar de precio (respecto a la lectura anterior) y está al
  menos un `DESCUENTO_MIN` % (50 %) por debajo de su **precio medio de los últimos
  99 días**, ponderado por el tiempo que estuvo a cada precio.
- El bot necesita al menos `HORAS_MIN_HISTORIAL` (24 h) de historial de un producto
  antes de avisar. Como empieza sin datos, la media cubre lo que ha visto hasta
  ese momento y va creciendo hasta los 99 días. Cada aviso dice cuántos días de
  historial tiene.
- El precio medio tiene que ser de al menos `PRECIO_MIN` (30 €).
- Un mismo producto no se repite durante 3 días, salvo que baje otro 5 %.

**Productos que se ignoran** porque no compensa revenderlos: ropa, muebles y otros
voluminosos (sofás, armarios, colchones, sillas, estanterías…), reacondicionados y
usados. Puedes añadir más palabras con la variable `EXCLUIR`.

## Configuración

En **Settings → Secrets and variables → Actions**:

- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Variable `BOT_ACTIVO` = `true` para que busque cada 5 minutos

Ajustes opcionales (pestaña Variables):

| Variable | Por defecto | Qué hace |
|---|---|---|
| `DESCUENTO_MIN` | `50` | % por debajo de la media de 99 días |
| `PRECIO_MIN` | `30` | Ignora productos cuyo precio medio sea menor (€) |
| `HORAS_MIN_HISTORIAL` | `24` | Historial mínimo de un producto antes de avisar |
| `EXCLUIR` | (nada) | Más palabras a ignorar, separadas por comas: `funko,peluche` |
| `TIENDAS` | (todas) | Solo estas, separadas por comas: `LDLC,GAME,Druni` |
| `MAX_AVISOS` | `15` | Mensajes con foto por búsqueda (el resto llega en un resumen) |
| `PAUSA_NOCHE` | `1-9` | Horas (Madrid) en las que no busca; `no` para buscar siempre |

De 1:00 a 9:00 (hora de Madrid) no se busca. Lanzado a mano con **Run workflow**
busca a cualquier hora.

El historial se guarda en la caché de GitHub Actions entre ejecuciones (solo los
cambios de precio de cada producto, así que ocupa poco).

## Probarlo en local

Solo necesita Python 3.10 o superior, sin dependencias:

```sh
python3 bot.py --simular                 # busca sin mandar ni guardar nada
python3 bot.py --simular --tienda GAME   # solo una tienda
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python3 bot.py --prueba                  # comprueba que llegan los mensajes
python3 bot.py --bucle 300               # busca cada 5 minutos sin parar
python3 -m unittest discover -s tests    # tests
```

## Añadir una tienda

Crea `tiendas/<tienda>.py` con `NOMBRE`, `FIJAS`, `ROTAR`, `POR_EJECUCION` y
`leer(html)` (devuelve una lista de `Producto`), y añádelo a `tiendas/__init__.py`.
