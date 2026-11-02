# App propia en Python, solo para Linux e integrada en Omarchy

LibrePods ya permite controlar AirPods en Linux. Aun así, construimos una app propia, usando LibrePods solo como referencia del protocolo de Apple (AAP). Lo que nos diferencia es la integración nativa con la barra de Omarchy, además de entender y controlar el código.

La idea original era multiplataforma, pero Windows no permite a una app normal abrir el canal Bluetooth clásico que necesitan los AirPods (L2CAP, PSM `0x1001`). Sin un driver del núcleo, como MagicAAP, solo se pueden leer batería y detección de oído, no cambiar el modo de ruido. macOS ya trae esta funcionalidad de serie. Por eso nos quedamos solo con Linux (BlueZ).

Elegimos Python porque su librería estándar abre sockets L2CAP en Linux sin dependencias y ya está instalado; para una herramienta de uso personal, la velocidad de desarrollo pesa más que la robustez de Rust.

## Considered Options

- **Contribuir a LibrePods o hacer un fork**: descartado; su interfaz no encaja con Omarchy y no aprenderíamos el protocolo.
- **Multiplataforma (Linux + Windows)**: descartado por la limitación de L2CAP en Windows descrita arriba.
- **Rust** (con `librepods-rs` como referencia) **o C++/Qt** (como LibrePods): descartados por coste inicial; Rust ni siquiera está instalado.
