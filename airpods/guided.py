"""Captura guiada: recorre las situaciones, marca el inicio y fin de cada una
y al final trocea la sesión en un archivo por situación."""

import json
import os

# Las situaciones con el estuche van al final porque cerrarlo desconecta los AirPods.
SITUATIONS = [
    ("modo-cancelacion", "Pulsa el tallo hasta tener Cancelación de ruido."),
    ("modo-transparencia", "Pulsa el tallo hasta tener Transparencia."),
    ("modo-adaptativo", "Pulsa el tallo hasta tener Adaptativo."),
    ("modo-desactivado", "Pulsa el tallo hasta tener Desactivado."),
    ("quitar-izquierdo", "Con ambos auriculares puestos, quítate el izquierdo."),
    ("poner-izquierdo", "Vuelve a ponerte el izquierdo."),
    ("quitar-derecho", "Quítate el derecho."),
    ("poner-derecho", "Vuelve a ponerte el derecho."),
    ("quitar-ambos", "Con ambos puestos, quítate los dos."),
    ("auricular-cargando", "Deja un auricular en el estuche (tapa abierta) cargando y el otro fuera."),
    ("bateria-estuche-abierto", "Con ambos auriculares dentro, abre el estuche."),
    ("bateria-estuche-cerrado", "Cierra el estuche y, cuando reconecten, ábrelo otra vez."),
]


_EAR_PREFIX = bytes.fromhex("040004000600")


def _got_expected(name, packets):
    if name.startswith(("poner-", "quitar-")):
        return any(p.startswith(_EAR_PREFIX) for p in packets)
    return bool(packets)


def run(capture, input_fn=input, print_fn=print, situations=SITUATIONS, only=None):
    if only:
        situations = [s for s in situations if s[0] in only]
    for name, instruction in situations:
        print_fn(f"\n== {name} ==\n{instruction}")
        reply = input_fn("Enter cuando estés listo (o 's' para saltar): ")
        if reply.strip().lower() == "s":
            continue
        while True:
            before = len(capture.rx_packets)
            capture.mark(f"inicio:{name}")
            input_fn("Hazlo ahora y pulsa Enter cuando termines: ")
            capture.mark(f"fin:{name}")
            if _got_expected(name, capture.rx_packets[before:]):
                break
            print_fn("AVISO: no llegó el paquete esperado de los AirPods.")
            if input_fn("Enter para repetirla, 's' para saltarla: ").strip().lower() == "s":
                break


def split(session_path, out_dir):
    """Escribe out_dir/<situacion>.jsonl con las líneas entre inicio y fin."""
    current, buffers = None, {}
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            label = entry.get("label", "")
            if entry["dir"] == "mark" and label.startswith("inicio:"):
                current = label[len("inicio:"):]
                buffers[current] = []
            elif entry["dir"] == "mark" and label.startswith("fin:"):
                if current:
                    buffers[current].append(line)
                current = None
                continue
            if current:
                buffers[current].append(line)
    written = []
    for name, lines in buffers.items():
        path = os.path.join(out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as out:
            out.writelines(lines)
        written.append(path)
    return written
