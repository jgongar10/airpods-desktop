"""Herramienta de terminal airpods."""

import argparse
import os
import socket
import sys

from .server import default_socket_path


def _default_out(line):
    print(line, flush=True)


def watch(socket_path=None, out=None, err=sys.stderr, stop_event=None):
    path = socket_path or os.environ.get("AIRPODS_SOCKET") or default_socket_path()
    emit = out or _default_out
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


def main(argv=None, socket_path=None, out=None, err=sys.stderr, stop_event=None):
    parser = argparse.ArgumentParser(prog="airpods")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("watch", help="muestra el estado como líneas JSON")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    if args.command == "watch":
        return watch(socket_path=socket_path, out=out, err=err, stop_event=stop_event)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
