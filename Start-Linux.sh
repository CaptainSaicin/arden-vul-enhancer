#!/usr/bin/env bash
set -u
cd "$(dirname "$0")" || exit 1

fail() {
    printf '\n%s\n' "$1" 'Read README.md for help.' >&2
    if [ -t 0 ]; then
        read -r -p 'Press Return to close. ' _answer
    fi
    exit 1
}

printf '\n%s\n' 'Arden Vul Enhancer' '------------------'
printf '%s\n' 'First-time setup needs internet access. Your PDF is processed only on your computer.'
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    fail 'Install Python 3.10 or newer through your distribution, then run this launcher again.'
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    fail 'Python Tk is missing. On Debian/Ubuntu install python3-tk and python3-venv; on other distributions install the corresponding Tk and venv packages.'
fi
if [ ! -x '.venv/bin/python' ]; then
    printf '\n%s\n' 'Creating a local Python environment…'
    python3 -m venv '.venv' || fail 'Could not create the local environment. Install the Python venv package and check folder permissions.'
fi
if ! '.venv/bin/python' -c 'import fitz, hashlib, pathlib, sys; p=pathlib.Path(".venv/.requirements.sha256"); wanted=hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest(); sys.exit(0 if p.exists() and p.read_text().strip()==wanted else 1)' >/dev/null 2>&1; then
    printf '\n%s\n' 'Installing the PDF dependency. This may take a minute…'
    '.venv/bin/python' -m pip install --disable-pip-version-check -r 'requirements.txt' || fail 'Setup did not finish. Check the connection and the error above.'
    '.venv/bin/python' -c 'import hashlib, pathlib; pathlib.Path(".venv/.requirements.sha256").write_text(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())' || fail 'Could not record completed setup.'
fi
'.venv/bin/python' -m arden_vul_enhancer --gui || fail 'The desktop app could not start. A graphical desktop session with Tk is required; see the README for command-line use.'
