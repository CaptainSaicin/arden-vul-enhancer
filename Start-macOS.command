#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1

fail() {
    printf '\n%s\n' "$1"
    printf '%s\n' 'Read README.md for help. Press Return to close this window.'
    read -r _answer
    exit 1
}

printf '\n%s\n' 'Arden Vul Enhancer' '------------------'
printf '%s\n' 'First-time setup needs internet access. Your PDF is processed only on your computer.'
AV_PYTHON=''
for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        AV_PYTHON="$candidate"
        break
    fi
done
if [ -z "$AV_PYTHON" ]; then
    fail 'Install Python 3.10 or newer from https://www.python.org/downloads/macos/ and run this launcher again.'
fi

if [ ! -x '.venv/bin/python' ]; then
    printf '\n%s\n' 'Creating a local Python environment…'
    "$AV_PYTHON" -m venv '.venv' || fail 'Could not create the local environment. Check that this folder is writable.'
fi
if ! '.venv/bin/python' -c 'import tkinter' >/dev/null 2>&1; then
    fail 'This Python installation does not include Tk. Use the Python.org macOS installer, then delete this project’s .venv folder and launch again.'
fi
if ! '.venv/bin/python' -c 'import fitz, hashlib, pathlib, sys; p=pathlib.Path(".venv/.requirements.sha256"); wanted=hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest(); sys.exit(0 if p.exists() and p.read_text().strip()==wanted else 1)' >/dev/null 2>&1; then
    printf '\n%s\n' 'Installing the PDF dependency. This may take a minute…'
    '.venv/bin/python' -m pip install --disable-pip-version-check -r 'requirements.txt' || fail 'Setup did not finish. Check the connection and the error above.'
    '.venv/bin/python' -c 'import hashlib, pathlib; pathlib.Path(".venv/.requirements.sha256").write_text(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())' || fail 'Could not record completed setup.'
fi
'.venv/bin/python' -m arden_vul_enhancer --gui || fail 'The desktop app could not start. Check the message above.'
