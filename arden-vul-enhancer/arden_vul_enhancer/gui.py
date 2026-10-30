"""Friendly, local desktop interface for Arden Vul Enhancer."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

from .engine import CancelledError, EnhancementError, EnhancementOptions, enhance_pdf


def suggested_output(source: str, navigation: bool, highlights: bool) -> str:
    """Suggest an unused filename without touching the input or filesystem."""
    if not source.strip():
        return ""
    source_path = Path(source).expanduser()
    suffix = "enhanced" if navigation and highlights else "navigation" if navigation else "highlighted"
    base = source_path.with_name(f"{source_path.stem}_{suffix}.pdf")
    candidate = base
    number = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}_{number}.pdf")
        number += 1
    return str(candidate)


def format_report(report: dict) -> str:
    """Present the engine's result in plain language, without technical IDs."""
    lines = [f"Saved: {Path(str(report.get('output', 'your enhanced PDF'))).name}"]
    if report.get("navigation"):
        lines.append(
            f"{int(report.get('links_added', 0)):,} hyperlinks added  |  "
            f"{int(report.get('bookmarks_total', 0)):,} bookmarks in the finished PDF"
        )
    if report.get("highlights"):
        lines.append(f"{int(report.get('highlights_added', 0)):,} color highlights added, with no comments")
    if report.get("color_key_page"):
        lines.append(f"Color key included on PDF page {int(report['color_key_page']):,}")
    if report.get("original_preserved"):
        lines.append("Your original PDF is unchanged.")
    warnings = report.get("warnings") or []
    if warnings:
        lines.extend(str(warning) for warning in warnings)
    return "\n".join(lines)


class EnhancerApp:
    """Keep all Tk operations on the main thread; PDF work runs in a worker."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Arden Vul Enhancer")
        self.root.geometry("900x780")
        self.root.minsize(860, 680)
        self.root.configure(background="#f4f6f8")
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self.close_when_done = False
        self.output_custom = False
        self.last_output: Path | None = None
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.navigation_var = tk.BooleanVar(value=True)
        self.highlights_var = tk.BooleanVar(value=True)
        self.key_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose your original complete-volume PDF to begin.")
        self.progress_var = tk.DoubleVar(value=0)
        self._configure_styles()
        self._build_window()
        self.source_var.trace_add("write", self._source_changed)
        self._refresh_options()
        self.root.after(100, self._drain_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        family = font.nametofont("TkDefaultFont").actual("family")
        style.configure("TFrame", background="#f4f6f8")
        style.configure("TLabel", background="#f4f6f8", foreground="#223040", font=(family, 10))
        style.configure("Title.TLabel", font=(family, 24, "bold"), foreground="#14293f")
        style.configure("Muted.TLabel", foreground="#536271", font=(family, 10))
        style.configure("Section.TLabel", font=(family, 12, "bold"))
        style.configure("TButton", padding=(12, 8), font=(family, 10))
        style.configure("Primary.TButton", background="#235f8e", foreground="white", font=(family, 11, "bold"))
        style.map("Primary.TButton", background=[("pressed", "#164569"), ("active", "#2c709e"), ("disabled", "#cbd4dc")],
                  foreground=[("disabled", "#667786")])
        style.configure("TCheckbutton", background="#f4f6f8", foreground="#223040", font=(family, 11))
        style.configure("Horizontal.TProgressbar", background="#2b7b94", troughcolor="#dce4ea", thickness=12)
        style.configure("TEntry", padding=7, font=(family, 10))

    def _build_window(self) -> None:
        viewport = ttk.Frame(self.root)
        viewport.pack(fill="both", expand=True)
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, background="#f4f6f8", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        outer = ttk.Frame(canvas, padding=(26, 22))
        content_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        def fit_content(_event=None) -> None:
            canvas.itemconfigure(content_window, width=canvas.winfo_width(),
                                 height=max(canvas.winfo_height(), outer.winfo_reqheight()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        def scroll_content(event) -> str | None:
            if isinstance(event.widget, tk.Text) or outer.winfo_height() <= canvas.winfo_height():
                return None
            direction = -1 if getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0 else 1
            canvas.yview_scroll(direction, "units")
            return "break"

        canvas.bind("<Configure>", fit_content)
        outer.bind("<Configure>", fit_content)
        for event_name in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind(event_name, scroll_content, add="+")
        self.content_canvas = canvas
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(9, weight=1)

        ttk.Label(outer, text="Arden Vul Enhancer", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="Choose the improvements you want. Create a new PDF for preparation and play.",
                  style="Muted.TLabel", wraplength=780).grid(row=1, column=0, sticky="w", pady=(5, 20))

        files = ttk.Frame(outer)
        files.grid(row=2, column=0, sticky="ew")
        files.columnconfigure(0, weight=1)
        ttk.Label(files, text="1. Your original PDF", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.source_entry = ttk.Entry(files, textvariable=self.source_var)
        self.source_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.source_browse = ttk.Button(files, text="Choose PDF...", command=self._choose_source)
        self.source_browse.grid(row=1, column=1, sticky="e")
        ttk.Label(files, text="Use the original 1,122-page Complete PDF. The app checks compatibility before editing.",
                  style="Muted.TLabel", wraplength=800).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 14))
        ttk.Label(files, text="Save the new copy as", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 7))
        self.output_entry = ttk.Entry(files, textvariable=self.output_var)
        self.output_entry.grid(row=4, column=0, sticky="ew", padx=(0, 10))
        self.output_entry.bind("<KeyRelease>", self._output_edited)
        self.output_browse = ttk.Button(files, text="Save as...", command=self._choose_output)
        self.output_browse.grid(row=4, column=1, sticky="e")

        ttk.Separator(outer).grid(row=3, column=0, sticky="ew", pady=(18, 16))
        choices = ttk.Frame(outer)
        choices.grid(row=4, column=0, sticky="ew")
        choices.columnconfigure(0, weight=1)
        choices.columnconfigure(1, weight=1)
        ttk.Label(choices, text="2. Choose your improvements", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.navigation_check = ttk.Checkbutton(choices, text="Bookmarks & hyperlinks", variable=self.navigation_var,
                                                command=self._refresh_options)
        self.navigation_check.grid(row=1, column=0, sticky="w")
        self.highlights_check = ttk.Checkbutton(choices, text="Color highlights", variable=self.highlights_var,
                                                command=self._refresh_options)
        self.highlights_check.grid(row=1, column=1, sticky="w")
        ttk.Label(choices, text="Jump to rooms, creatures, items, and references.", style="Muted.TLabel",
                  wraplength=370).grid(row=2, column=0, sticky="nw", padx=(24, 20), pady=(4, 8))
        ttk.Label(choices, text="Reviewed GM markup, including treasure and discoveries.", style="Muted.TLabel",
                  wraplength=370).grid(row=2, column=1, sticky="nw", padx=(24, 0), pady=(4, 8))
        self.key_check = ttk.Checkbutton(choices, text="Include a color-key page at the end", variable=self.key_var)
        self.key_check.grid(row=3, column=1, sticky="w", padx=(24, 0), pady=(0, 10))

        legend = ttk.Frame(outer)
        legend.grid(row=5, column=0, sticky="ew", pady=(3, 17))
        for i, (label, background, foreground) in enumerate([
            ("Red - Creatures", "#fde3e4", "#853542"),
            ("Blue - Traps & hazards", "#deebfd", "#245685"),
            ("Yellow - GM info & treasure", "#fff2b9", "#6e5819"),
            ("Green - Player text", "#dff2e4", "#285f3d"),
        ]):
            legend.columnconfigure(i, weight=1)
            tk.Label(legend, text=label, background=background, foreground=foreground,
                     padx=9, pady=7, font=font.nametofont("TkDefaultFont")).grid(row=0, column=i, sticky="ew", padx=(0, 5 if i < 3 else 0))

        ttk.Label(outer, textvariable=self.status_var, wraplength=780).grid(row=6, column=0, sticky="w", pady=(0, 8))
        self.progress_bar = ttk.Progressbar(outer, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=7, column=0, sticky="ew")

        actions = ttk.Frame(outer)
        actions.grid(row=8, column=0, sticky="ew", pady=(14, 10))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, text="Local processing. Your original stays unchanged.", style="Muted.TLabel",
                  wraplength=360).grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(10, 8))
        self.create_button = ttk.Button(actions, text="Create enhanced PDF", style="Primary.TButton", command=self._start)
        self.create_button.grid(row=0, column=2)

        result_frame = ttk.Frame(outer)
        result_frame.grid(row=9, column=0, sticky="nsew", pady=(5, 0))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.result_box = tk.Text(result_frame, height=5, wrap="word", relief="flat", borderwidth=0,
                                  background="#f4f6f8", foreground="#34485a", font=font.nametofont("TkDefaultFont"),
                                  state="disabled", cursor="arrow", takefocus=False)
        self.result_box.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.open_button = ttk.Button(result_frame, text="Open output folder", command=self._open_output_folder, state="disabled")
        self.open_button.grid(row=0, column=1, sticky="se")

    def _source_changed(self, *_args) -> None:
        if not self.busy and not self.output_custom:
            self._suggest_output()
        if not self.busy:
            self.status_var.set("Ready. Choose your improvements, then create your new copy." if self.source_var.get().strip()
                                else "Choose your original complete-volume PDF to begin.")
        self._refresh_buttons()

    def _suggest_output(self) -> None:
        try:
            path = suggested_output(self.source_var.get(), self.navigation_var.get(), self.highlights_var.get())
        except (OSError, ValueError):
            path = ""
        self.output_var.set(path)

    def _output_edited(self, _event=None) -> None:
        self.output_custom = bool(self.output_var.get().strip())

    def _refresh_options(self) -> None:
        self.key_check.configure(state="normal" if self.highlights_var.get() and not self.busy else "disabled")
        if not self.output_custom and not self.busy:
            self._suggest_output()
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        available = bool(self.source_var.get().strip()) and (self.navigation_var.get() or self.highlights_var.get()) and not self.busy
        self.create_button.configure(state="normal" if available else "disabled")

    def _choose_source(self) -> None:
        filename = filedialog.askopenfilename(parent=self.root, title="Choose your original Arden Vul Complete PDF",
                                              filetypes=[("PDF documents", ("*.pdf", "*.PDF")), ("All files", "*")])
        if filename:
            self.output_custom = False
            self.source_var.set(filename)
            self.status_var.set("Ready. Choose navigation, highlights, or both, then create your new copy.")

    def _choose_output(self) -> None:
        current = Path(self.output_var.get()).expanduser() if self.output_var.get().strip() else None
        filename = filedialog.asksaveasfilename(parent=self.root, title="Choose a new PDF filename", defaultextension=".pdf",
                                                initialdir=str(current.parent) if current else None,
                                                initialfile=current.name if current else "Arden_Vul_enhanced.pdf",
                                                filetypes=[("PDF documents", "*.pdf")], confirmoverwrite=False)
        if filename:
            self.output_custom = True
            self.output_var.set(filename)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for widget in (self.source_entry, self.output_entry, self.source_browse, self.output_browse,
                       self.navigation_check, self.highlights_check):
            widget.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.open_button.configure(state="normal" if self.last_output and not busy else "disabled")
        self.key_check.configure(state="normal" if self.highlights_var.get() and not busy else "disabled")
        self._refresh_buttons()

    def _show_result(self, text: str) -> None:
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text)
        self.result_box.configure(state="disabled")

    def _start(self) -> None:
        if self.busy:
            return
        try:
            source = Path(self.source_var.get().strip()).expanduser().resolve()
            target_text = self.output_var.get().strip()
            if not source.is_file():
                raise ValueError("Choose an existing original PDF first.")
            if not target_text:
                raise ValueError("Choose where to save the enhanced PDF.")
            target = Path(target_text).expanduser().resolve()
            if source == target:
                raise ValueError("Choose a different output filename. The original PDF must stay unchanged.")
            if target.suffix.lower() != ".pdf":
                raise ValueError("The new filename must end in .pdf.")
            if target.exists():
                raise ValueError("That output file already exists. Choose a new filename with Save as.")
            if not target.parent.is_dir():
                raise ValueError("The output folder does not exist. Choose an existing folder with Save as.")
            if not (self.navigation_var.get() or self.highlights_var.get()):
                raise ValueError("Select bookmarks & hyperlinks, color highlights, or both.")
            options = EnhancementOptions(navigation=self.navigation_var.get(), highlights=self.highlights_var.get(),
                                         add_color_key=self.highlights_var.get() and self.key_var.get())
        except (OSError, ValueError) as error:
            messagebox.showerror("Check your files", str(error), parent=self.root)
            return

        self.last_output = None
        self._show_result("")
        self.progress_var.set(0)
        self.status_var.set("Checking the PDF... Large books can take a few minutes. You can cancel at any time.")
        self.cancel_event = threading.Event()
        cancellation = self.cancel_event
        self._set_busy(True)

        def progress(fraction: float, message: str) -> None:
            self.events.put(("progress", (fraction, message)))

        def work() -> None:
            try:
                report = enhance_pdf(source, target, options, progress=progress, cancel=cancellation)
                self.events.put(("done", report))
            except CancelledError:
                self.events.put(("cancelled", None))
            except EnhancementError as error:
                self.events.put(("error", str(error)))
            except Exception as error:
                # Keep the application usable after a filesystem or dependency
                # failure; the message retains the useful underlying cause.
                self.events.put(("error", f"The PDF could not be created.\n\n{error}\n\nYour original PDF was not changed."))

        threading.Thread(target=work, name="arden-vul-worker", daemon=True).start()

    def _cancel(self) -> None:
        if self.busy:
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Cancelling safely... Waiting for the current PDF operation to finish.")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    fraction, message = payload
                    self.progress_var.set(max(0, min(100, float(fraction) * 100)))
                    if not self.cancel_event.is_set():
                        self.status_var.set(str(message))
                elif kind == "done":
                    self.last_output = Path(str(payload["output"]))
                    self._set_busy(False)
                    self.progress_var.set(100)
                    self.status_var.set("Your enhanced PDF is ready.")
                    self._show_result(format_report(payload))
                    if self.close_when_done:
                        self.root.destroy()
                        return
                elif kind == "cancelled":
                    self._set_busy(False)
                    self.progress_var.set(0)
                    self.status_var.set("Cancelled. Your original PDF is unchanged.")
                    if self.close_when_done:
                        self.root.destroy()
                        return
                elif kind == "error":
                    self._set_busy(False)
                    self.progress_var.set(0)
                    self.status_var.set("No enhanced PDF was created. Check the message and try again.")
                    if self.close_when_done:
                        self.root.destroy()
                        return
                    messagebox.showerror("Unable to create the PDF", payload, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _open_output_folder(self) -> None:
        if not self.last_output:
            return
        folder = str(self.last_output.parent)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as error:
            messagebox.showinfo("Your output folder", f"Your PDF is saved here:\n\n{self.last_output}\n\nCould not open the folder automatically: {error}", parent=self.root)

    def _close(self) -> None:
        if self.busy:
            if messagebox.askyesno("Cancel and close?", "A PDF is still being processed. Cancel the operation and close when it is safe?", parent=self.root):
                self.close_when_done = True
                self._cancel()
        else:
            self.root.destroy()


def main() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"The desktop window could not open: {error}", file=sys.stderr)
        print("Use a desktop session with Tk installed, or run python -m arden_vul_enhancer --help for command-line options.", file=sys.stderr)
        return 1
    EnhancerApp(root)
    root.mainloop()
    return 0
