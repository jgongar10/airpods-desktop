# airpods-desktop

App de escritorio para ver el estado y cambiar la configuración de unos AirPods desde un ordenador que no es de Apple.

## Language

### Dispositivo

**AirPods**:
El conjunto emparejado de dos auriculares y su estuche, tratado como un único dispositivo. El modelo de referencia son los AirPods 4 con cancelación activa de ruido.
_Avoid_: cascos, headset, dispositivo Bluetooth

**Auricular**:
Cada una de las dos piezas (izquierdo o derecho) de los AirPods.
_Avoid_: bud, pod, earbud

**Estuche**:
La caja de carga de los AirPods.
_Avoid_: case, funda

### Estado y configuración

**Batería**:
El nivel de carga y el estado de carga (cargando o no) de cada auricular y del estuche, reportado por separado.
_Avoid_: pila, carga total

**Modo de ruido**:
El modo de escucha activo de los AirPods: Cancelación de ruido, Transparencia, Adaptativo o Desactivado.
_Avoid_: ANC (para el modo en general), modo de escucha, noise mode

**Detección de oído**:
Saber si cada auricular está puesto en el oído o no, y pausar o reanudar la reproducción en consecuencia.
_Avoid_: ear detection, sensor de proximidad

**Pausa automática**:
Una pausa de la reproducción provocada por la app al quitarse un auricular. Solo una pausa automática se reanuda sola al volver a poner el auricular; una pausa hecha por el usuario nunca.
_Avoid_: autopausa, pausa inteligente

### Interfaz

**Widget**:
El indicador de los AirPods en la barra de Omarchy; solo es visible mientras los AirPods están conectados.
_Avoid_: applet, icono de bandeja, indicador

**Panel**:
La vista que se despliega al hacer clic en el widget, con la batería de cada pieza, el modo de ruido y el interruptor de detección de oído.
_Avoid_: popup, menú, ventana
