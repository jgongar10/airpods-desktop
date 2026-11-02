"""Captura guiada: recorre las situaciones, marca el inicio y fin de cada una
y al final trocea la sesión en un archivo por situación."""

import json
import os

SITUATIONS = [
    ("bateria-estuche-abierto", "Abre el estuche con ambos auriculares dentro."),
    ("bateria-estuche-cerrado", "Cierra el estuche (los AirPods pueden desconectarse; espera a que reconecten abriéndolo)."),
    ("auricular-cargando", "Deja un auricular en el estuche cargando y saca el otro."),
    ("modo-cancelacion", "Pulsa el tallo hasta tener Cancelación de ruido."),
    ("modo-transparencia", "Pulsa el tallo hasta tener Transparencia."),
    ("modo-adaptativo", "Pulsa el tallo hasta tener Adaptativo."),
    ("modo-desactivado", "Pulsa el tallo hasta tener Desactivado."),
    ("poner-izquierdo", "Con el izquierdo fuera del oído, ponte el izquierdo."),
    ("quitar-izquierdo", "Quítate el izquierdo."),
    ("poner-derecho", "Con el derecho fuera del oído, ponte el derecho."),
    ("quitar-derecho", "Quítate el derecho."),
    ("quitar-ambos", "Con ambos puestos, quítatelos los dos."),
]


def run(capture, input_fn=input, print_fn=print, situations=SITUATIONS):
    for name, instruction in situations:
        print_fn(f"\n== {name} ==\n{instruction}")
        reply = input_fn("Enter cuando estés listo (o 's' para saltar): ")
        if reply.strip().lower() == "s":
            continue
        capture.mark(f"inicio:{name}")
        input_fn("Hazlo ahora y pulsa Enter cuando termines: ")
        capture.mark(f"fin:{name}")


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
