"""Open the desktop app by default; arguments select the command-line tool."""
from __future__ import annotations

import sys


def self_check() -> int:
    """Verify packaged editing data without opening Tk or requiring a book."""
    import collections
    import json

    from . import __version__
    from .engine import EnhancementError, load_patch

    try:
        import tkinter
        tcl_version = tkinter.Tcl().eval("info patchlevel")
        patch = load_patch()
        counts = {
            "links": sum(len(items) for items in patch["navigation"]["links"].values()),
            "bookmarks": len(patch["navigation"]["bookmarks"]),
            "highlights": sum(len(items) for items in patch["highlights"]["pages"].values()),
        }
        expected = {"links": 44338, "bookmarks": 3929, "highlights": 19890}
        if patch["schema_version"] != 1 or len(patch["source"]["pages"]) != 1122:
            raise ValueError("Editing data schema or source-page count is incorrect.")
        if counts != expected or any(patch["counts"].get(key) != value for key, value in counts.items()):
            raise ValueError("Editing data counts do not match the reviewed release.")
        by_color = collections.Counter(item["category"] for items in patch["highlights"]["pages"].values() for item in items)
        if dict(by_color) != patch["counts"]["highlights_by_color"] or set(by_color) != {"red", "blue", "yellow", "green"}:
            raise ValueError("Highlight color counts are inconsistent.")
        print(json.dumps({"status": "ok", "version": __version__, "patch_version": patch.get("patch_version"),
                          "data_available": True, "tcl_version": tcl_version, "expected_source_pages": patch["source"]["page_count"],
                          "counts": counts, "highlights_by_color": dict(by_color)}, indent=2))
        return 0
    except (EnhancementError, KeyError, TypeError, ValueError, ImportError, RuntimeError) as error:
        print(json.dumps({"status": "error", "data_available": False, "message": str(error)}), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--self-check"]:
        return self_check()
    if not arguments or arguments == ["--gui"]:
        try:
            from .gui import main as gui_main
        except ImportError as error:
            print(f"The desktop app could not load: {error}", file=sys.stderr)
            print("Run the source launcher to install dependencies. If Tk is unavailable, use --help for the command-line tool.", file=sys.stderr)
            return 1
        return gui_main()
    from .cli import main as cli_main
    return cli_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
