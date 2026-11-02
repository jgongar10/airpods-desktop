# airpods-desktop

App de escritorio para Linux (BlueZ) e integrada de forma nativa en la barra de **Omarchy** (Hyprland + Quickshell) para ver el estado y controlar unos **AirPods 4 con cancelación activa de ruido** mediante el protocolo de accesorios de Apple (**AAP**, L2CAP `0x1001`).

## Qué hace

- **Batería en vivo**: muestra en el **Widget** de la barra el porcentaje del auricular con menos carga conocida y, al hacer clic, despliega el **Panel** con la batería del **Auricular** izquierdo, el derecho y el **Estuche** por separado (con indicador de carga y estado `Desconocida` cuando la pieza no reporta nivel).
- **Modo de ruido**: permite ver y cambiar entre **Cancelación de ruido** (`cancelacion`), **Transparencia** (`transparencia`), **Adaptativo** (`adaptativo`) y **Desactivado** (`desactivado`) tanto desde el Panel como desde la terminal, y refleja los cambios hechos pulsando el tallo de los AirPods.
- **Detección de oído y Pausa automática**: pausa todos los reproductores MPRIS que estén sonando al quitarte un auricular y reanuda únicamente esos al volver a ponértelo (sin reanudar pausas manuales ni cuando te quitas ambos auriculares). La preferencia se puede activar o desactivar y se recuerda entre reinicios.
- **Reconexión y reintentos automáticos**: detecta los AirPods automáticamente por el fabricante Apple (`0x004C`) en cuanto el sistema los conecta, sin configurar su dirección MAC, y reintenta el canal AAP si se pierde la comunicación.

## Requisitos

- Linux con **BlueZ** y **systemd** de usuario.
- **Python 3** (librería estándar) y **PyGObject** (`python-gobject`, incluido en el sistema) para D-Bus.
- **Omarchy** (`omarchy-shell` / Quickshell) para el Widget y el Panel de la barra.

## Instalación

Instalación en un solo paso en el usuario actual (sin `sudo` / root):

```bash
./install.sh
```

Esto:
1. Enlaza la herramienta `airpods` en `~/.local/bin/airpods`.
2. Crea, habilita y arranca el servicio `~/.config/systemd/user/airpods.service`.
3. Enlaza y habilita el plugin `airpods` en `~/.config/omarchy/plugins/airpods` y lo coloca junto al icono de Bluetooth en la barra de Omarchy.

Para desinstalar y dejar el sistema como estaba:

```bash
./install.sh --uninstall
```

## Uso desde la terminal (`airpods`)

```bash
# Ver el estado actual y cada cambio en vivo como líneas JSON
airpods watch

# Cambiar el modo de ruido (ideal para atajos de teclado en Hyprland)
airpods mode cancelacion
airpods mode transparencia
airpods mode adaptativo
airpods mode desactivado

# Activar o desactivar la detección de oído
airpods ear-detection on
airpods ear-detection off
```

### Formato JSON de `airpods watch`

```json
{
  "connected": true,
  "communicating": true,
  "battery": {
    "left": { "level": 85, "charging": false },
    "right": { "level": 90, "charging": false },
    "case": { "level": null, "charging": false }
  },
  "noise_mode": "cancelacion",
  "in_ear": { "left": true, "right": true },
  "ear_detection": true
}
```

## Estructura del proyecto

- `airpods/aap.py` — Traducción pura (sin E/S) de paquetes del protocolo AAP (saludo, batería, modo de ruido, rol primario y detección de oído).
- `airpods/link.py` — Canal Bluetooth clásico `AF_BLUETOOTH` / `BTPROTO_L2CAP` en el PSM `0x1001`.
- `airpods/bluez.py` — Detección de conexión y desconexión en BlueZ por D-Bus (fabricante Apple `0x004C`).
- `airpods/mpris.py` — Control y escucha de reproductores multimedia MPRIS por D-Bus.
- `airpods/core.py` — Núcleo del servicio: estado, reglas de Pausa automática, persistencia de configuración y reintentos de comunicación.
- `airpods/server.py` — Servidor de control local por socket Unix (`$XDG_RUNTIME_DIR/airpods.sock`).
- `airpods/cli.py` y `bin/airpods` — Herramienta de línea de comandos `airpods`.
- `plugin/airpods/` — Plugin de barra y Panel en QML para `omarchy-shell`.
- `docs/captures/` — Capturas reales etiquetadas de los AirPods 4 usadas en las pruebas automáticas.

## Desarrollo y pruebas

Ejecutar la batería de pruebas automáticas (no requiere AirPods físicos conectados):

```bash
python3 -m unittest discover -s tests -v
```

Ver los registros del servicio en tiempo real:

```bash
journalctl --user -u airpods.service -f
```
