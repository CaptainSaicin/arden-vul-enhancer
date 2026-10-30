"""Optional command-line entry point; the default launcher opens the GUI."""
import argparse
import json
import sys
from . import __version__
from .engine import EnhancementError, EnhancementOptions, enhance_pdf, inspect_pdf


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply reviewed navigation and/or color highlights to your own Arden Vul Complete PDF.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("input", help="Original 1,122-page Complete PDF")
    parser.add_argument("output", nargs="?", help="New output PDF (must not already exist)")
    parser.add_argument("--mode", choices=("navigation", "highlights", "both"), default="both")
    parser.add_argument("--no-color-key", action="store_true", help="Do not append the color-key page")
    parser.add_argument("--check", action="store_true", help="Check compatibility without creating an output")
    parser.add_argument("--quiet", action="store_true", help="Print only the final JSON report")
    args = parser.parse_args(argv)
    if not args.check and not args.output:
        parser.error("output is required unless --check is used")
    last = [-1]
    def progress(fraction, message):
        pct = int(fraction * 100)
        if not args.quiet and pct != last[0]:
            print(f"{pct:3d}%  {message}", file=sys.stderr, flush=True)
            last[0] = pct
    try:
        if args.check:
            result = inspect_pdf(args.input, progress=progress)
        else:
            options = EnhancementOptions(args.mode in ("navigation", "both"), args.mode in ("highlights", "both"), not args.no_color_key)
            result = enhance_pdf(args.input, args.output, options, progress=progress)
        print(json.dumps(result, indent=2))
        return 0
    except EnhancementError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
