# User guide

## What you need

- Your own original **The Halls of Arden Vul Complete** PDF with the supported 1,122-page layout.
- Enough free space for a separate enhanced copy and a temporary output while it is being written.
- Either the desktop download for your operating system or Python 3.10 or later with the source project. Python 3.12 is recommended for source use.

The desktop app processes the file on your own computer. It does not send the PDF to GitHub, the developer, or an AI service.

## Using the desktop app

1. **Download and extract.** Choose the correct ZIP from the project's Releases page. Extract all of it to a normal folder. On Windows and Linux, keep the executable and its `_internal` folder together.
2. **Open the app.** Windows uses `Arden-Vul-Enhancer.exe`; macOS uses `Arden-Vul-Enhancer.app`; Linux uses the executable named `Arden-Vul-Enhancer`.
3. **Choose the original PDF.** Use the file chooser rather than typing a path.
4. **Choose your updates.** Select navigation, highlights, or both. Selecting neither is not allowed.
5. **Choose the color key.** If highlights are selected, you can include a one-page explanation of the colors after the original book. Turning it off keeps the original page count.
6. **Choose an output filename.** Use a different filename from the original. The app suggests an appropriate suffix.
7. **Create the enhanced copy.** The progress display shows compatibility checks and processing. You can cancel. The final copy is made available only after processing succeeds.
8. **Open the result.** The completion message identifies the saved file. Use the button to open its folder, then open the PDF in your preferred reader.

For later changes in your choices, start again from the original PDF and save another output. That gives you clean, separate versions for navigation only, highlights only, or both.

## What each choice does

### Navigation

This adds the reviewed hyperlink rectangles and destinations and builds the updated bookmark navigation. It includes internal cross-references and the original printed external OSRIC link. Existing source content stays in place.

### Highlights

This adds the reviewed red, blue, yellow, and green highlights. They are ordinary PDF highlight annotations, so readers that support annotation editing can modify them. No explanatory text is stored in their comment fields.

Yellow includes treasure and discoverable items, along with the instructions needed to locate, access, identify, retrieve, or operate them. A trapped chest's valuables can therefore be yellow while the trap's trigger and harm are blue.

Green marks text suitable to share **when the source makes it available to the characters**. For example, a translated inscription still requires the relevant discovery and language conditions. A rumor remains a rumor.

### Both

This applies the same navigation and highlighting together. It does not perform a new AI analysis; it uses the reviewed patch supplied with this release.

## Running from source

Download the source ZIP, extract it, and keep the folder structure intact. In particular, keep `arden_vul_enhancer/data/patch.json.gz` with the application.

### Windows

1. Install Python from [python.org](https://www.python.org/downloads/windows/). Python 3.12 is a suitable choice.
2. Double-click `Start-Windows.bat` in the extracted project folder.
3. On first use, the launcher creates `.venv`, installs the dependency, and opens the app. It displays setup errors if Python cannot be found.

You can also open a terminal in the project folder and run:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m arden_vul_enhancer
```

### macOS

Use a Python installation that includes Tkinter, such as the standard installer from [python.org](https://www.python.org/downloads/macos/). See [Python's official macOS guide](https://docs.python.org/3/using/mac.html).

Open Terminal in the extracted project folder and run:

```bash
bash Start-macOS.command
```

This also works when a downloaded archive did not retain the launcher's executable permission. After setup, you can run `.venv/bin/python -m arden_vul_enhancer` from that folder.

### Linux

Install Python and Tkinter using your distribution's package manager if necessary. On Ubuntu or Debian:

```bash
sudo apt install python3 python3-venv python3-tk
```

Then open a terminal in the extracted project folder:

```bash
bash Start-Linux.sh
```

The source route is often the best choice on Linux distributions with older system libraries than the prebuilt package. The provided Linux workflow builds on Ubuntu 24.04.

## Common questions

### The app says my PDF is not compatible

Use the original complete-volume PDF. The patch requires the book's original text and placement to match its known layout. A scan, an OCR-only version, individual volumes, a different edition, changed pagination, or shifted text can fail this check. Separate vendor watermark lines are acceptable only when the original book's text and position are unchanged.

Do not force the coordinates onto a rejected document. If you report a compatibility issue, include the app's error message, your operating system, and the PDF's page count. You do not need to upload the book to a public issue.

### I only want hyperlinks, or I only want highlights

Select the corresponding update and leave the other unchecked. Highlights-only preserves the original navigation; navigation-only does not add highlight colors. A color key is relevant only when highlights are selected.

### Can I overwrite my original?

The app requires a separate output path. Keep your original copy so you can apply a different option later.

### The program does not launch after I extract the desktop ZIP

Make sure you extracted the complete archive. Do not copy the Windows executable or Linux executable away from the accompanying `_internal` folder. Confirm that you downloaded the package matching your operating system and, on Mac, your processor type.

If an unsigned application is blocked by the operating system, check that the download came from the repository you intended. The project does not include a Windows signing certificate or Apple notarization. You can use the readable source project instead. For macOS's own review controls, see [Apple's guidance on safely opening apps](https://support.apple.com/en-us/102445).

### I see `No module named tkinter`

Tkinter is part of many Python installations, but Linux often packages it separately. Install your distribution's Python Tk package. On macOS, use the standard Python installer with Tk support. The prebuilt desktop downloads bundle their runtime.

### The first setup cannot download a dependency

The source launcher's first run needs the internet to install PyMuPDF. Retry with a working connection. It uses a local `.venv`, so administrative access is not normally required for that dependency installation. The downloaded desktop app does not need this setup step.

### The highlights look different in different PDF readers

PDF readers can display annotation opacity and selection outlines differently. Use a reader with PDF annotation support. The highlights are not flattened into the page artwork, and their comments are empty.

### Can I use this on a different adventure?

This release is specific to the supported Arden Vul Complete layout. The patch contains reviewed coordinates for that book, not a general-purpose automatic hyperlinking or highlighting model.

### Can I share the resulting PDF?

The tool's software license covers its code and original patch instructions. It does not grant rights to redistribute the commercial book or the enhanced copy. Share the utility so other owners can process their own copies.

## Command line

Run `python -m arden_vul_enhancer --help` from the project folder. The core forms are:

```bash
python -m arden_vul_enhancer "original.pdf" --check
python -m arden_vul_enhancer "original.pdf" "output.pdf" --mode navigation
python -m arden_vul_enhancer "original.pdf" "output.pdf" --mode highlights
python -m arden_vul_enhancer "original.pdf" "output.pdf" --mode both --no-color-key
```

`--quiet` reduces progress output. `--version` displays the app version. Put filenames containing spaces inside quotes.
