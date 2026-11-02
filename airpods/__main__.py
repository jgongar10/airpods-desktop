import sys

if any(arg in ("--capture", "--guided", "--only") for arg in sys.argv[1:]):
    from .service import main
else:
    from .cli import main

raise SystemExit(main())
