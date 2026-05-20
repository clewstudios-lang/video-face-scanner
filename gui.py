import io
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import database as db
import scanner as sc
import video_player as vp


def _resource_path(rel: str) -> str:
    """Resolve a bundled-asset path, working both in dev and inside a PyInstaller one-file build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


_ICON_PATH = _resource_path(os.path.join("assets", "icon.png"))


def fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def make_timestamp_link(parent, video_path: str, timestamp_sec: float,
                        status_setter=None, text: str = None,
                        font=None):
    """Create a clickable tk.Label that opens the video at the given second.

    `status_setter` (optional): a callable(str) used to show feedback (e.g. "Opened in VLC at 75s").
    """
    label = tk.Label(
        parent,
        text=text or fmt_time(timestamp_sec),
        fg="#1565c0",
        cursor="hand2",
        bg=parent.cget("background") if "background" in parent.keys() else None,
        font=font or ("TkDefaultFont", 9, "underline"),
    )

    def on_click(_event=None):
        result = vp.open_video_at(video_path, timestamp_sec)
        if status_setter:
            status_setter(result)

    def on_enter(_event=None):
        label.config(fg="#0a3d91")

    def on_leave(_event=None):
        label.config(fg="#1565c0")

    label.bind("<Button-1>", on_click)
    label.bind("<Enter>", on_enter)
    label.bind("<Leave>", on_leave)
    return label


class VideoFaceScanner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Face Scanner")
        self.geometry("960x620")
        self.minsize(760, 520)
        self._set_icon()
        db.init_db()
        self._known: list = []          # [(person_id, name, encoding), ...]
        self._face_queue: list = []     # pending unknown face dicts
        self._seen_unknown_encs: list = []  # de-dup buffer for current scan
        self._scan_running = False
        self._load_known()
        self._build_ui()

    def _set_icon(self):
        try:
            img = Image.open(_ICON_PATH)
            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _load_known(self):
        self._known = db.get_all_encodings()

    def _refresh_persons_list(self):
        self.persons_box.delete(0, tk.END)
        self._pid_list = []
        for pid, name, count in db.get_person_counts():
            self.persons_box.insert(tk.END, f"{name}  ({count})")
            self._pid_list.append(pid)
        persons = db.get_all_persons()
        names = [r[1] for r in persons]
        self._name_to_pid = {r[1]: r[0] for r in persons}
        if hasattr(self, "search_combo"):
            self.search_combo["values"] = names

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = ttk.LabelFrame(paned, text="Known Persons", width=210)
        paned.add(left, weight=1)
        self._build_left(left)

        right = ttk.Frame(paned)
        paned.add(right, weight=4)
        self._build_right(right)

    def _build_left(self, parent):
        lf = ttk.Frame(parent)
        lf.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(lf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.persons_box = tk.Listbox(lf, yscrollcommand=sb.set, activestyle="dotbox")
        self.persons_box.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self.persons_box.yview)

        bf = ttk.Frame(parent)
        bf.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(bf, text="View Appearances", command=self._view_appearances).pack(fill=tk.X, pady=1)
        ttk.Button(bf, text="Rename Person",    command=self._rename_person).pack(fill=tk.X, pady=1)
        ttk.Button(bf, text="Delete Person",    command=self._delete_person).pack(fill=tk.X, pady=1)

        self._pid_list = []
        self._name_to_pid = {}
        self._refresh_persons_list()

    def _build_right(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb

        scan_tab = ttk.Frame(nb)
        nb.add(scan_tab, text="  Scan Video  ")
        self._build_scan_tab(scan_tab)

        search_tab = ttk.Frame(nb)
        nb.add(search_tab, text="  Search  ")
        self._build_search_tab(search_tab)

    def _build_scan_tab(self, parent):
        # Top controls row
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=10, pady=8)

        ttk.Button(top, text="Select Video & Scan", command=self._start_scan).pack(side=tk.LEFT)

        ttk.Label(top, text="   Every").pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=10)
        ttk.Spinbox(top, from_=1, to=120, width=5, textvariable=self.interval_var).pack(side=tk.LEFT, padx=2)
        ttk.Label(top, text="frames").pack(side=tk.LEFT)

        ttk.Label(top, text="   Workers").pack(side=tk.LEFT)
        cpu_max = max(1, (os.cpu_count() or 2))
        self.workers_var = tk.IntVar(value=min(3, cpu_max))
        ttk.Spinbox(top, from_=1, to=cpu_max, width=4, textvariable=self.workers_var).pack(side=tk.LEFT, padx=2)
        ttk.Label(top, text="(1 = single-threaded)", foreground="#888").pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(top, text="Stop", command=self._stop_scan, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # Video name + progress
        self.video_name_var = tk.StringVar(value="No video selected.")
        ttk.Label(parent, textvariable=self.video_name_var, foreground="#555").pack(
            anchor=tk.W, padx=10
        )

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(parent, variable=self.progress_var, maximum=100).pack(
            fill=tk.X, padx=10, pady=3
        )
        self.status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.status_var, foreground="#333").pack(
            anchor=tk.W, padx=10
        )

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=6)

        ttk.Label(parent, text="Unidentified Faces — Please Name:", font=("TkDefaultFont", 10, "bold")).pack(
            anchor=tk.W, padx=10
        )

        # Face review area
        self.review_frame = ttk.Frame(parent)
        self.review_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._show_review_idle()

    def _build_search_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top, text="Person:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_combo = ttk.Combobox(top, textvariable=self.search_var, state="readonly", width=28)
        self.search_combo.pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Find", command=self._do_search).pack(side=tk.LEFT)

        self.search_status_var = tk.StringVar(value="Tip: click a timecode to jump to it (VLC/mpv recommended).")
        ttk.Label(parent, textvariable=self.search_status_var, foreground="#666",
                  font=("TkDefaultFont", 8)).pack(anchor=tk.W, padx=10)

        # Scrollable results
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._search_canvas = tk.Canvas(container, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._search_canvas.yview)
        self.search_results = ttk.Frame(self._search_canvas)
        self.search_results.bind(
            "<Configure>",
            lambda e: self._search_canvas.configure(scrollregion=self._search_canvas.bbox("all")),
        )
        self._search_canvas.create_window((0, 0), window=self.search_results, anchor=tk.NW)
        self._search_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._search_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Scan logic
    # ------------------------------------------------------------------

    def _start_scan(self):
        if self._scan_running:
            return
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.MP4 *.avi *.AVI *.mov *.MOV *.mkv *.MKV *.wmv *.WMV *.flv *.FLV *.m4v *.M4V *.webm *.WEBM"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self._scan_running = True
        self._face_queue.clear()
        self._seen_unknown_encs.clear()
        self._load_known()
        self.progress_var.set(0)
        self.video_name_var.set(f"Scanning: {os.path.basename(path)}")
        self.status_var.set("Starting…")
        self.stop_btn.config(state=tk.NORMAL)
        self._show_review_idle()

        threading.Thread(target=self._scan_thread, args=(path,), daemon=True).start()

    def _stop_scan(self):
        self._scan_running = False

    def _scan_thread(self, video_path):
        try:
            interval = self.interval_var.get()
            workers = max(1, self.workers_var.get())

            if workers > 1:
                def progress(current, total, in_flight, n_workers):
                    pct = (current / total * 100) if total > 0 else 0.0
                    self.after(0, self._on_progress_parallel, pct, current, total, in_flight, n_workers)

                source = sc.scan_video_parallel(video_path, interval, workers, progress)
            else:
                def progress(current, total):
                    if total > 0:
                        pct = current / total * 100
                        self.after(0, self._on_progress, pct, current, total)

                source = sc.scan_video(video_path, interval, progress)

            for face_data in source:
                if not self._scan_running:
                    break

                face_data["video_path"] = video_path
                person_id, name, confidence = sc.match_face(face_data["encoding"], self._known)

                if person_id is not None and confidence > 50.0:
                    db.add_appearance(
                        person_id, video_path,
                        face_data["frame_number"], face_data["timestamp_sec"],
                        face_data["thumbnail"],
                    )
                else:
                    if sc.is_new_unknown(face_data["encoding"], self._seen_unknown_encs):
                        self._seen_unknown_encs.append(face_data["encoding"])
                        face_data["candidate_name"] = name
                        face_data["candidate_confidence"] = confidence
                        self.after(0, self._enqueue_unknown, face_data)

            self.after(0, self._on_scan_done, video_path)

        except Exception as exc:
            self.after(0, messagebox.showerror, "Scan Error", str(exc))
            self.after(0, self._on_scan_done, video_path)

    def _on_progress(self, pct, current, total):
        self.progress_var.set(pct)
        self.status_var.set(
            f"Single-threaded · frame {current:,} / {total:,} · "
            f"{len(self._face_queue)} new face(s) to review"
        )

    def _on_progress_parallel(self, pct, completed, total, in_flight, n_workers):
        self.progress_var.set(pct)
        self.status_var.set(
            f"{n_workers} workers in parallel · {completed:,}/{total:,} frames processed · "
            f"{in_flight} in flight · {len(self._face_queue)} face(s) to review"
        )

    def _on_scan_done(self, video_path):
        self._scan_running = False
        self.progress_var.set(100)
        self.stop_btn.config(state=tk.DISABLED)
        self.video_name_var.set(f"Done: {os.path.basename(video_path)}")
        pending = len(self._face_queue)
        self.status_var.set(
            f"Scan complete.  {pending} unidentified face(s) remaining."
            if pending else "Scan complete. All faces identified."
        )
        self._refresh_persons_list()

    # ------------------------------------------------------------------
    # Face review UI
    # ------------------------------------------------------------------

    def _enqueue_unknown(self, face_data):
        self._face_queue.append(face_data)
        if len(self._face_queue) == 1:
            self._render_review()

    def _show_review_idle(self):
        for w in self.review_frame.winfo_children():
            w.destroy()
        ttk.Label(
            self.review_frame,
            text="No unidentified faces pending.",
            foreground="#888",
        ).pack(pady=30)

    def _render_review(self):
        for w in self.review_frame.winfo_children():
            w.destroy()

        if not self._face_queue:
            ttk.Label(self.review_frame, text="All done — no more faces to review.", foreground="green").pack(pady=30)
            return

        face = self._face_queue[0]
        remaining = len(self._face_queue)

        outer = ttk.Frame(self.review_frame)
        outer.pack(expand=True, pady=10)

        # Thumbnail
        try:
            img = Image.open(io.BytesIO(face["thumbnail"])).resize((160, 160), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = ttk.Label(outer, image=photo)
            lbl.image = photo
            lbl.pack()
        except Exception:
            ttk.Label(outer, text="[image unavailable]").pack()

        # Timestamp info
        ts = fmt_time(face["timestamp_sec"])
        ttk.Label(outer, text=f"Found at {ts}  (frame {face['frame_number']:,})").pack(pady=(4, 0))
        ttk.Label(outer, text=os.path.basename(face["video_path"]), foreground="#666",
                  font=("TkDefaultFont", 8)).pack()
        ttk.Label(outer, text=f"{remaining} face(s) remaining in queue",
                  foreground="#888").pack(pady=(2, 10))

        # Confidence hint
        candidate = face.get("candidate_name")
        conf = face.get("candidate_confidence", 0.0)
        if candidate and conf > 0:
            hint_color = "#b07000" if conf >= 30 else "#888888"
            ttk.Label(
                outer,
                text=f"Best guess: {candidate}  ({conf:.0f}% confidence — below auto-match threshold)",
                foreground=hint_color,
                font=("TkDefaultFont", 9, "italic"),
            ).pack(pady=(0, 6))

        # Name input
        input_frame = ttk.LabelFrame(outer, text="Who is this person?", padding=8)
        input_frame.pack(fill=tk.X, pady=4)

        persons = db.get_all_persons()
        name_var = tk.StringVar()

        if persons:
            ttk.Label(input_frame, text="Pick existing:").grid(row=0, column=0, sticky=tk.W)
            combo = ttk.Combobox(input_frame, textvariable=name_var,
                                  values=[p[1] for p in persons], state="readonly", width=26)
            combo.grid(row=0, column=1, padx=6, sticky=tk.W)
            if candidate and candidate in [p[1] for p in persons]:
                name_var.set(candidate)

        ttk.Label(input_frame, text="New name:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        entry = ttk.Entry(input_frame, width=28)
        entry.grid(row=1, column=1, padx=6, pady=(6, 0), sticky=tk.W)
        entry.focus_set()

        def get_name():
            return entry.get().strip() or name_var.get().strip()

        def save():
            n = get_name()
            if not n:
                messagebox.showwarning("Name required", "Please type a name or pick one from the list.")
                return
            pid = db.add_person(n)
            db.add_face_encoding(pid, face["encoding"])
            db.add_appearance(pid, face["video_path"], face["frame_number"],
                              face["timestamp_sec"], face["thumbnail"])
            self._load_known()
            self._refresh_persons_list()
            self._face_queue.pop(0)
            self._render_review()

        def skip():
            self._face_queue.pop(0)
            self._render_review()

        btn_row = ttk.Frame(outer)
        btn_row.pack(pady=8)
        ttk.Button(btn_row, text="Save & Next", command=save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Skip",        command=skip).pack(side=tk.LEFT, padx=6)

        entry.bind("<Return>", lambda _e: save())

    # ------------------------------------------------------------------
    # Person list actions
    # ------------------------------------------------------------------

    def _selected_person(self):
        sel = self.persons_box.curselection()
        if not sel:
            messagebox.showinfo("Select person", "Click a name in the list first.")
            return None, None
        idx = sel[0]
        pid = self._pid_list[idx]
        name = db.get_all_persons()
        for p in name:
            if p[0] == pid:
                return pid, p[1]
        return pid, "Unknown"

    def _view_appearances(self):
        pid, name = self._selected_person()
        if pid is None:
            return
        rows = db.get_appearances_by_person(pid)
        AppearancesWindow(self, name, rows)

    def _rename_person(self):
        pid, name = self._selected_person()
        if pid is None:
            return
        new = simpledialog.askstring("Rename", f"New name for '{name}':", initialvalue=name)
        if new and new.strip():
            db.rename_person(pid, new.strip())
            self._load_known()
            self._refresh_persons_list()

    def _delete_person(self):
        pid, name = self._selected_person()
        if pid is None:
            return
        if messagebox.askyesno("Delete", f"Delete '{name}' and all their appearances?"):
            db.delete_person(pid)
            self._load_known()
            self._refresh_persons_list()

    # ------------------------------------------------------------------
    # Search tab
    # ------------------------------------------------------------------

    def _do_search(self):
        name = self.search_var.get()
        if not name or name not in self._name_to_pid:
            messagebox.showinfo("Select person", "Please choose a person from the dropdown.")
            return
        pid = self._name_to_pid[name]
        rows = db.get_appearances_by_person(pid)

        for w in self.search_results.winfo_children():
            w.destroy()

        if not rows:
            ttk.Label(self.search_results, text="No appearances on record.").pack(pady=20)
            return

        # Group by video file
        by_video: dict = {}
        for video_path, frame_no, ts, thumb, _ in rows:
            by_video.setdefault(video_path, []).append((frame_no, ts, thumb))

        for video_path, frames in by_video.items():
            lf = ttk.LabelFrame(self.search_results, text=os.path.basename(video_path), padding=6)
            lf.pack(fill=tk.X, padx=6, pady=4)
            ttk.Label(lf, text=video_path, foreground="#666",
                      font=("TkDefaultFont", 8), wraplength=560).pack(anchor=tk.W)

            timecodes_row = tk.Frame(lf)
            timecodes_row.pack(anchor=tk.W, pady=2, fill=tk.X)
            ttk.Label(timecodes_row, text="Timecodes:").pack(side=tk.LEFT)
            for _, ts, _ in frames:
                link = make_timestamp_link(
                    timecodes_row, video_path, ts,
                    status_setter=lambda msg: self.search_status_var.set(msg),
                )
                link.pack(side=tk.LEFT, padx=4)

            ttk.Label(lf, text=f"{len(frames)} appearance(s)", foreground="#555").pack(anchor=tk.W)


# ------------------------------------------------------------------
# Appearances popup window
# ------------------------------------------------------------------

class AppearancesWindow(tk.Toplevel):
    def __init__(self, parent, name: str, rows: list):
        super().__init__(parent)
        self.title(f"Appearances — {name}")
        self.geometry("720x500")

        if not rows:
            ttk.Label(self, text="No appearances recorded yet.").pack(pady=30)
            return

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        canvas = tk.Canvas(container, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        by_video: dict = {}
        for video_path, frame_no, ts, thumb, _ in rows:
            by_video.setdefault(video_path, []).append((frame_no, ts, thumb))

        self._photos = []  # keep references

        self.status_var = tk.StringVar(value="Tip: click a thumbnail or timecode to open the video at that point.")
        ttk.Label(self, textvariable=self.status_var, foreground="#666",
                  font=("TkDefaultFont", 8)).pack(anchor=tk.W, padx=10, pady=(0, 6))

        for video_path, frames in by_video.items():
            ttk.Label(inner, text=os.path.basename(video_path),
                      font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W, pady=(10, 2))
            ttk.Label(inner, text=video_path, foreground="#777",
                      font=("TkDefaultFont", 8)).pack(anchor=tk.W)

            grid = ttk.Frame(inner)
            grid.pack(fill=tk.X, pady=4)

            for i, (frame_no, ts, thumb) in enumerate(frames[:30]):
                cell = ttk.Frame(grid)
                cell.grid(row=i // 6, column=i % 6, padx=4, pady=4)

                def open_at(_ev=None, p=video_path, t=ts):
                    self.status_var.set(vp.open_video_at(p, t))

                if thumb:
                    try:
                        img = Image.open(io.BytesIO(thumb)).resize((90, 90), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self._photos.append(photo)
                        thumb_lbl = tk.Label(cell, image=photo, cursor="hand2", borderwidth=2,
                                             relief="flat", highlightthickness=0)
                        thumb_lbl.pack()
                        thumb_lbl.bind("<Button-1>", open_at)
                        thumb_lbl.bind("<Enter>", lambda _e, w=thumb_lbl: w.config(relief="raised"))
                        thumb_lbl.bind("<Leave>", lambda _e, w=thumb_lbl: w.config(relief="flat"))
                    except Exception:
                        ttk.Label(cell, text="[img]").pack()

                link = make_timestamp_link(
                    cell, video_path, ts,
                    status_setter=lambda msg: self.status_var.set(msg),
                    font=("TkDefaultFont", 8, "underline"),
                )
                link.pack()
