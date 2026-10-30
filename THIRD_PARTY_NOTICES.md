# License and third-party notices

## Arden Vul Enhancer

Copyright (C) 2026 Arden Vul Enhancer contributors.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License in `LICENSE` for details.

The AGPL license applies to the program code and the contributors' original patch instructions. It does not apply to The Halls of Arden Vul, its book text, illustrations, maps, or other publisher-owned material. Those are not included in this repository. No affiliation with or endorsement by the book's authors or publisher is implied.

## PyMuPDF and MuPDF

The runtime dependency is **PyMuPDF 1.26.6**, which includes MuPDF functionality. PyMuPDF/MuPDF are available under their own AGPL and commercial licensing terms from Artifex. This project uses the open-source dependency and retains its notices; it does not supply a commercial Artifex license.

- [Version-specific package metadata and license declaration](https://pypi.org/project/PyMuPDF/1.26.6/)
- [Upstream license text for version 1.26.6](https://github.com/pymupdf/PyMuPDF/blob/1.26.6/COPYING)
- [Upstream license and copyright documentation](https://github.com/pymupdf/PyMuPDF/blob/main/docs/about.rst)
- [MuPDF project](https://mupdf.com/)

The desktop builder copies available installed dependency license files into `dependency-notices/` and includes the full corresponding source of this utility as `Arden-Vul-Enhancer-source.zip` in each platform archive.

## PyInstaller

**PyInstaller 6.22.3** is a build dependency. It is licensed under GPLv2-or-later with an exception permitting distribution of the applications it bundles under their own licenses. This does not replace the licenses of this application or its dependencies.

- [PyInstaller package](https://pypi.org/project/pyinstaller/6.22.3/)
- [PyInstaller license and bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)

## Python, Tcl/Tk, and platform libraries

Packaged desktop downloads include a Python interpreter and the libraries required by Tkinter. Python uses the Python Software Foundation license; Tcl/Tk and other bundled components retain their respective licenses and notices. The builder preserves library files collected by PyInstaller and copies an interpreter license when supplied by the local Python distribution.

- [Python license](https://docs.python.org/3/license.html)
- [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html)

Do not remove dependency notices when redistributing the desktop packages. For modified releases, provide the corresponding source and license information required by the applicable licenses.
