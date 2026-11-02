# Capturas reales de los AirPods

Ejemplos reales capturados de unos **AirPods 4 con cancelación activa de ruido** (`Modalias: bluetooth:v004Cp201Bd215C`, modelos `A3055` / `A3056`) en Linux sobre BlueZ y L2CAP `0x1001` sin root. Alimentan los AirPods simulados de las pruebas automáticas (ticket #2).

## Formato

Cada archivo es JSON Lines (una entrada por línea):

- `{"ts": <epoch s>, "dir": "tx"|"rx", "hex": "<bytes en hex>"}`: paquete enviado o recibido por el canal L2CAP `0x1001`.
- `{"ts": <epoch s>, "dir": "mark", "label": "inicio:<situacion>"|"fin:<situacion>"}`: marca de inicio y fin de la situación.

## Cómo se capturaron

Con el servicio del repositorio:

```bash
# Captura libre (permite escribir etiquetas y pulsar Enter)
python3 -m airpods --capture docs/captures/<archivo>.jsonl

# Captura guiada (marca inicio/fin por situación y trocea la sesión)
python3 -m airpods --guided docs/captures
python3 -m airpods --guided docs/captures --only quitar-izquierdo,poner-izquierdo,quitar-derecho,poner-derecho,quitar-ambos
```

Durante la primera sesión apareció un detalle importante del protocolo: tras abrir L2CAP `0x1001`, los AirPods recién reconectados tardan ~300–500 ms en contestar al saludo (`00 00 04 00 …` → `01 00 04 00 …`). Si `SET_SPECIFIC_FEATURES` y `REQUEST_NOTIFICATIONS` se envían antes de recibir `01 00 04 00 …`, el firmware los descarta y no emite notificaciones de batería (`0x04`) ni de oído (`0x06`). `airpods/link.py` espera esa confirmación antes de suscribirse.

## Qué situación representa cada archivo

### Batería y estuche

Capturados en la primera sesión real al pasar de tener ambos auriculares puestos con el estuche cerrado a guardar primero el derecho y luego el izquierdo abriendo el estuche:

| Archivo | Situación | Paquete(s) clave observados |
|---|---|---|
| `bateria-estuche-cerrado.jsonl` | Conexión inicial con ambos auriculares puestos y el estuche cerrado (incluye saludo `tx`/`rx` y volcado inicial). | `04000400040003 0401640201 0201640201 0801000401`: izquierdo (`04`) 100 % descargando (`02`), derecho (`02`) 100 % descargando (`02`), estuche (`08`) desconectado (`status=04`, `level=00`). También contiene `04000400080001000100` (auricular primario = izquierdo `01`) y `0400040006000000` (ambos en el oído). |
| `auricular-cargando.jsonl` | Auricular derecho recién metido en el estuche cargando; auricular izquierdo fuera; estuche aún sin reportar carga. | `0400040006000002` (primario en el oído `00`, secundario en el estuche `02`) y `04000400040003 0401640201 0201640101 0801ff0401` (derecho `02` con `status=01` cargando; estuche `08` con `level=ff`, `status=04` desconocido). |
| `bateria-estuche-abierto.jsonl` | Ambos auriculares dentro del estuche cargando con la tapa abierta reportando la batería del estuche. | `0400040006000202` (ambos en el estuche) y `04000400040003 0401640101 0201640101 0801240201`: izquierdo y derecho al 100 % cargando (`01`), estuche (`08`) al 36 % (`0x24`) con `status=02`. Incluye el paquete previo transitorio con `0801ff0401` justo antes de que el estuche comunique su nivel. |

### Modo de ruido

Notificaciones `04 00 04 00 09 00 0d <modo> 00 00 00` (`01` Desactivado, `02` Cancelación de ruido, `03` Transparencia, `04` Adaptativo):

| Archivo | Situación | Cómo se obtuvo |
|---|---|---|
| `modo-desactivado.jsonl` | Cambio a **Desactivado** (`01`). | Pulsación física del tallo (`rx 0400040009000d01000000`). |
| `modo-cancelacion.jsonl` | Cambio a **Cancelación de ruido** (`02`). | Pulsación física del tallo (`rx 0400040009000d02000000`). |
| `modo-transparencia.jsonl` | Cambio a **Transparencia** (`03`). | Pulsación física del tallo (`rx 0400040009000d03000000`). |
| `modo-adaptativo.jsonl` | Cambio a **Adaptativo** (`04`). | El ciclo del tallo configurado en estos AirPods no incluía Adaptativo; se envió la orden AAP `tx 0400040009000d04000000` por el canal real y se capturó la notificación de confirmación `rx 0400040009000d04000000` de los AirPods. |

### Detección de oído

Capturados en una única sesión guiada continua (`sesion-oido.jsonl`) empezando con ambos auriculares puestos. En esta sesión el auricular primario era el **derecho** (`040004000800 02 00 01 00` en el volcado inicial de `sesion-oido.jsonl`, frente a `01` izquierdo en `bateria-estuche-cerrado.jsonl`), por lo que en `04 00 04 00 06 00 <primario> <secundario>` el primer byte corresponde al derecho y el segundo al izquierdo (`00` en el oído, `01` fuera del oído, `02` en el estuche):

| Archivo | Situación | Paquete(s) `0x06` observados |
|---|---|---|
| `sesion-oido.jsonl` | Sesión completa con saludo, estado inicial (`0x04`, `0x08`, `0x06`) y las cinco acciones siguientes en secuencia. | Inicial: `04000400080002000100` (primario = derecho) y `0400040006000000` (ambos puestos). |
| `quitar-izquierdo.jsonl` | Con ambos puestos, quitarse el auricular izquierdo. | `0400040006000001` (derecho puesto `00`, izquierdo fuera `01`). |
| `poner-izquierdo.jsonl` | Volver a ponerse el auricular izquierdo. | `0400040006000000` (ambos puestos `00 00`). |
| `quitar-derecho.jsonl` | Con ambos puestos, quitarse el auricular derecho. | `0400040006000100` (derecho fuera `01`, izquierdo puesto `00`). |
| `poner-derecho.jsonl` | Volver a ponerse el auricular derecho. | `0400040006000000` (ambos puestos `00 00`). |
| `quitar-ambos.jsonl` | Con ambos puestos, quitarse los dos auriculares. | `0400040006000100` seguido a los 15 ms de `0400040006000101` (ambos fuera `01 01`). |
