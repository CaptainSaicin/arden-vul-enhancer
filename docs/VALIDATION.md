# Validation for version 1.0.0

The three update modes were exercised against the supported original **1,122-page Arden Vul Complete PDF**. These checks verify the application of the reviewed patch and preservation of the source document.

## Results on the complete book

The highlights and both-mode runs below included the optional color-key page.

| Mode | Output pages | Added hyperlinks | Total bookmarks | Added highlights |
| --- | ---: | ---: | ---: | ---: |
| Navigation only | 1,122 | 44,338 | 3,929 | 0 |
| Highlights only | 1,123 | 0 | 3,670 | 19,890 |
| Both | 1,123 | 44,338 | 3,930 | 19,890 |

In highlights-only mode, the original **3,669 bookmarks** are preserved and one bookmark points to the appended key. Navigation mode uses the reviewed **3,929-bookmark** outline; both mode adds the key bookmark to that outline.

The highlight totals are **3,887 red**, **1,018 blue**, **11,455 yellow**, and **3,530 green**. These count PDF highlight annotations, which may span several lines; they are not counts of distinct creatures, traps, or items.

For each of the three modes:

- All **1,122 original pages** were checked for unchanged text, page content streams, and geometry.
- Every generated hyperlink, highlight, and bookmark was compared with the expected destinations, labels, colors, and positions from the reference or retained source navigation, as applicable.
- Generated highlight comment fields were absent.
- The original PDF's checksum was unchanged after processing.

## Automated regression tests

**Eleven synthetic tests passed.** They cover the update modes and important failure paths, including compatibility checks, cancellation, refusal to overwrite a destination, and preservation of an original `/Fit` bookmark when adding only the color key.

The public tests generate small synthetic documents and do not require the commercial book. Run them from the project folder with:

```bash
python -m unittest discover -s tests -v
```

## Desktop packaging

A **clean local Linux PyInstaller build** completed successfully. Its packaged self-check loaded the actual processing engine, compressed patch data, and Tcl runtime successfully.

The actual desktop window was visually inspected, including its scrollable layout at the minimum window size. Eleven GUI interaction checks passed using synthetic files and a mocked processing callback: option combinations, filenames, progress, completion, cancellation, and source/output protection were covered. The full-book processing checks above exercised the real engine separately. The rebuilt Linux executable also opened successfully with Python environment overrides cleared.

The included GitHub workflow provides native Windows, Apple-silicon Mac, Intel Mac, and Linux build jobs. **Windows and macOS native builds have not been executed in this development environment.** Their downloads should be published after the corresponding GitHub jobs succeed and the applications have been checked on the intended systems.

No commercial PDF, extracted adventure prose, private source path, or private checksum is included in this validation record or required by the public build workflow.
