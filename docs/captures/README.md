# Capturas reales de los AirPods

Ejemplos que usarán las pruebas automáticas (ticket #2). Aquí se explica qué situación representa cada archivo y cómo se capturó.

## Cómo capturar

```
python3 -m airpods --capture docs/captures/<situacion>.jsonl
```

Con los AirPods conectados por el sistema, el servicio abre L2CAP `0x1001`, hace el saludo y vuelca los paquetes. Formato JSON Lines, una línea por paquete:

- `{"ts": <epoch s>, "dir": "rx"|"tx", "hex": "<bytes>"}`
- `{"ts": ..., "dir": "mark", "label": "..."}`: etiqueta que se escribe por teclado (Enter) justo antes de hacer la acción física.

Los primeros paquetes (`tx` saludo, `rx` confirmación y estado inicial) aparecen en cada captura.

## Situaciones a capturar

| Archivo | Acción | Estado |
|---|---|---|
| `bateria-estuche-abierto.jsonl` | Abrir el estuche con ambos auriculares dentro | pendiente |
| `bateria-estuche-cerrado.jsonl` | Cerrar el estuche | pendiente |
| `auricular-cargando.jsonl` | Auricular dentro del estuche cargando | pendiente |
| `modo-cancelacion.jsonl`, `modo-transparencia.jsonl`, `modo-adaptativo.jsonl`, `modo-desactivado.jsonl` | Cambiar con el tallo a cada modo | pendiente |
| `poner-izquierdo.jsonl`, `quitar-izquierdo.jsonl`, `poner-derecho.jsonl`, `quitar-derecho.jsonl` | Ponerse / quitarse cada auricular | pendiente |
| `quitar-ambos.jsonl` | Quitarse ambos | pendiente |

Una captura por situación, con una etiqueta `mark` antes de cada acción para localizar el paquete.
