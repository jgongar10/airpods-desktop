"""Herramienta de terminal airpods."""

import argparse
import json
import os
import socket
import sys

from . import aap
from .server import default_socket_path


def _default_out(line):
    print(line, flush=True)


def _resolve_socket(socket_path):
    return socket_path or os.environ.get("AIRPODS_SOCKET") or default_socket_path()


def _connect_socket(socket_path, err):
    path = _resolve_socket(socket_path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        print(
            "Error: el servicio de AirPods no está en marcha.",
            file=err,
            flush=True,
        )
        sock.close()
        return None
    return sock


def _send_command(payload, socket_path, err):
    sock = _connect_socket(socket_path, err)
    if sock is None:
        return 1
    try:
        req = json.dumps(payload) + "\n"
        sock.sendall(req.encode("utf-8"))
        f = sock.makefile("r", encoding="utf-8")
        line = f.readline()
        if not line:
            print("Error: sin respuesta del servicio.", file=err, flush=True)
            return 1
        resp = json.loads(line)
        if not resp.get("ok"):
            print(resp.get("error") or "Error al ejecutar la orden.", file=err, flush=True)
            return 1
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return 0


def watch(socket_path=None, out=None, err=sys.stderr, stop_event=None):
    emit = out or _default_out
    sock = _connect_socket(socket_path, err)
    if sock is None:
        return 1
    try:
        sock.sendall(b'{"cmd": "watch"}\n')
        f = sock.makefile("r", encoding="utf-8")
        for line in f:
            emit(line.rstrip("\n"))
            if stop_event is not None and stop_event.is_set():
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return 0


def set_mode(mode, socket_path=None, err=sys.stderr):
    if mode not in aap.NOISE_MODES:
        valid = ", ".join(aap.NOISE_MODES)
        print(
            f"Error: modo de ruido no válido '{mode}'. Modos válidos: {valid}.",
            file=err,
            flush=True,
        )
        return 2
    return _send_command({"cmd": "mode", "mode": mode}, socket_path, err)


def set_ear_detection(value, socket_path=None, err=sys.stderr):
    normalized = str(value).strip().lower()
    if normalized not in ("on", "off"):
        print(
            f"Error: valor no válido '{value}'. Usa 'on' u 'off'.",
            file=err,
            flush=True,
        )
        return 2
    return _send_command(
        {"cmd": "ear-detection", "enabled": normalized == "on"},
        socket_path,
        err,
    )


def main(argv=None, socket_path=None, out=None, err=sys.stderr, stop_event=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        from .gui import run_app

        return run_app(socket_path=socket_path)

    parser = argparse.ArgumentParser(prog="airpods")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("app", help="abre la aplicación de escritorio")
    sub.add_parser("gui", help="abre la aplicación de escritorio")
    sub.add_parser("watch", help="muestra el estado como líneas JSON")
    mode_parser = sub.add_parser("mode", help="cambia el modo de ruido")
    mode_parser.add_argument("value", help="cancelacion | transparencia | adaptativo | desactivado")
    ear_parser = sub.add_parser("ear-detection", help="activa o desactiva la detección de oído")
    ear_parser.add_argument("value", help="on | off")
    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    if args.command in ("app", "gui"):
        from .gui import run_app

        return run_app(socket_path=socket_path)
    if args.command == "watch":
        return watch(socket_path=socket_path, out=out, err=err, stop_event=stop_event)
    if args.command == "mode":
        return set_mode(args.value, socket_path=socket_path, err=err)
    if args.command == "ear-detection":
        return set_ear_detection(args.value, socket_path=socket_path, err=err)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
