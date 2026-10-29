# Error de precio

Bot gratuito que cada 5 minutos revisa las ofertas más nuevas de
[Chollometro](https://www.chollometro.com/nuevos) y te avisa por Telegram de las
que están **al menos un 50 % por debajo de su precio habitual**, o que alguien
ha marcado como "error de precio". Cubre Amazon y el resto de tiendas (Fnac,
El Corte Inglés, Lidl, PcComponentes…).

No usa ninguna API de pago. Amazon y CamelCamelCamel bloquean a los bots, pero
los errores de precio se publican en Chollometro en cuestión de minutos, junto con
el precio habitual del producto.

## Puesta en marcha (≈5 minutos, todo desde el móvil)

1. **Crea el bot de Telegram**: abre [@BotFather](https://t.me/BotFather), escribe
   `/newbot` y guarda el *token* que te da. Después mándale cualquier mensaje a tu
   bot nuevo (si no, no puede escribirte).
2. **Consigue tu chat ID**: abre [@userinfobot](https://t.me/userinfobot) y copia
   el número que aparece como `Id`.
3. En GitHub, ve a **Settings → Secrets and variables → Actions**:
   - Pestaña **Secrets** → *New repository secret*:
     - `TELEGRAM_BOT_TOKEN` = el token del paso 1
     - `TELEGRAM_CHAT_ID` = el número del paso 2
4. **Pruébalo**: pestaña **Actions → Buscar errores de precio → Run workflow**.
   En unos segundos te deberían llegar los chollos actuales.
5. **Actívalo cada 5 min**: en la pestaña **Variables** crea `BOT_ACTIVO` = `true`.
   Para pararlo, bórrala o ponla a `false`.

> ⚠️ **Coste de GitHub Actions**: en un repositorio **público** es gratis e
> ilimitado. En uno **privado** solo hay 2.000 minutos gratis al mes y ejecutarlo
> cada 5 minutos gasta unos 8.600, así que GitHub lo pararía a mitad de mes (no te
> cobra nada salvo que hayas puesto un límite de gasto). Haz el repo público en
> *Settings → General → Danger Zone → Change visibility*: tus claves siguen ocultas
> en Secrets. Si prefieres mantenerlo privado, cambia el cron a `*/30 * * * *`.

GitHub no garantiza los 5 minutos exactos: cuando hay mucha carga, el cron puede
retrasarse 10-15 minutos.

## Ajustes opcionales (pestaña Variables)

| Variable        | Por defecto | Qué hace                                              |
|-----------------|-------------|-------------------------------------------------------|
| `DESCUENTO_MIN` | `50`        | % mínimo por debajo del precio habitual               |
| `PRECIO_MIN`    | `1`         | Ignora productos más baratos que esto (€)             |
| `TIENDAS`       | (todas)     | Solo estas tiendas, separadas por comas: `Amazon,Fnac` |
| `PAGINAS`       | `2`         | Páginas de "nuevos" que revisa (≈30 ofertas cada una) |
| `MAX_AVISOS`    | `15`        | Máximo de mensajes por búsqueda                       |

Cada oferta se avisa una sola vez (durante 7 días).

## Ejecutarlo en tu propio servidor o Raspberry Pi

Solo necesita Python 3.9 o superior, sin dependencias:

```sh
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python3 bot.py --prueba      # comprueba que llegan los mensajes
python3 bot.py --bucle 300   # busca cada 5 minutos sin parar
```

## Tests

```sh
python3 -m unittest discover -s tests
```
