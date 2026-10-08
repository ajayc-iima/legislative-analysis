"""Dispatch: trial (OCR benchmark) or extract (three-field pipeline)."""

import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args and args[0] in ("trial", "extract") else "trial"
    rest = args[1:] if args and args and args[0] == command else args
    if command == "extract":
        from .extract import main as run
    else:
        from .trial import main as run
    return run(rest)


if __name__ == "__main__":
    raise SystemExit(main())
