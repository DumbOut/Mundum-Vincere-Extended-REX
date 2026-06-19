#!/usr/bin/env python3
"""
DMB Slave Texture Duplicator GUI

Purpose:
  Reads export_descr_unit.txt ownership, finds the soldier/officer/mount model types
  used by selected factions, then patches descr_model_battle.txt by adding missing
  texture lines for those factions copied from each DMB block's slave texture.

Default factions:
  cisra_01, itanos_01, massilia_01, thamud_01, kos_01

Run:
  python dmb_slave_texture_gui.py
"""
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

DEFAULT_FACTIONS = "cisra_01, itanos_01, massilia_01, thamud_01, kos_01"
MOUNT_MAP = {
    "light horse": "horse_light",
    "medium horse": "horse_medium",
    "heavy horse": "horse_heavy",
    "generals horse": "generals_horse",
}


def parse_factions(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,\s]+", text) if x.strip()]


def parse_edu_models(edu_text: str, targets: list[str]):
    models_by_faction = {f: set() for f in targets}
    units_by_faction = {f: [] for f in targets}

    for block in re.split(r"(?m)^type\s+", edu_text)[1:]:
        lines = block.splitlines()
        unit_type = lines[0].strip() if lines else ""
        own = re.search(r"(?m)^ownership\s+(.+)$", block)
        if not own:
            continue
        owners = [x.strip() for x in re.split(r"[,\s]+", own.group(1).strip()) if x.strip()]

        refs = []
        soldier = re.search(r"(?m)^soldier\s+([^,\n]+)", block)
        if soldier:
            refs.append(soldier.group(1).strip())
        refs.extend(x.strip() for x in re.findall(r"(?m)^officer\s+([^,\n]+)", block))
        mount = re.search(r"(?m)^mount\s+([^,\n]+)", block)
        if mount:
            raw_mount = mount.group(1).strip()
            refs.append(MOUNT_MAP.get(raw_mount, raw_mount))

        for faction in targets:
            if faction in owners:
                units_by_faction[faction].append(unit_type)
                models_by_faction[faction].update(refs)

    return models_by_faction, units_by_faction


def split_dmb_blocks(dmb_text: str):
    matches = list(re.finditer(r"(?m)^type\s+.*$", dmb_text))
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(dmb_text)
        yield start, end, dmb_text[start:end]


def dmb_type_name(block: str) -> str | None:
    match = re.match(r"(?m)^type\s+(.+)$", block)
    return match.group(1).strip() if match else None


def parse_texture_line(line: str):
    match = re.match(r"^(\s*texture\s+)(.+)$", line)
    if not match:
        return None
    prefix = match.group(1)
    parts = [p.strip() for p in match.group(2).strip().split(",")]
    if len(parts) < 2:
        return None
    return prefix, parts[:-1], parts[-1]


def patch_dmb(dmb_text: str, edu_text: str, factions: list[str]):
    models_by_faction, units_by_faction = parse_edu_models(edu_text, factions)
    wanted = {}
    for faction, models in models_by_faction.items():
        for model in models:
            wanted.setdefault(model, set()).add(faction)

    blocks = list(split_dmb_blocks(dmb_text))
    found_types = {dmb_type_name(block) for _, _, block in blocks}
    missing_types = sorted(set(wanted) - found_types)

    output = []
    pos = 0
    changes = []

    for start, end, block in blocks:
        output.append(dmb_text[pos:start])
        pos = end
        type_name = dmb_type_name(block)
        target_factions = sorted(wanted.get(type_name, []), key=factions.index) if type_name in wanted else []
        if not target_factions:
            output.append(block)
            continue

        lines = block.splitlines(keepends=True)
        existing_factions = set()
        texture_infos = []
        for idx, line in enumerate(lines):
            raw = line.rstrip("\n")
            parsed = parse_texture_line(raw)
            if parsed:
                prefix, texture_factions, path = parsed
                existing_factions.update(texture_factions)
                texture_infos.append((idx, prefix, texture_factions, path, raw))

        slave_only = [x for x in texture_infos if x[2] == ["slave"]]
        slave_any = [x for x in texture_infos if "slave" in x[2]]
        source = slave_only[0] if slave_only else (slave_any[0] if slave_any else None)
        if not source:
            output.append(block)
            continue

        idx, prefix, _texture_factions, path, raw_source = source
        new_lines = []
        added = []
        newline_suffix = "\n" if lines[idx].endswith("\n") else ""
        for faction in target_factions:
            if faction not in existing_factions:
                new_lines.append(f"{prefix}{faction}, {path}{newline_suffix}")
                added.append(faction)

        if new_lines:
            lines[idx + 1:idx + 1] = new_lines
            changes.append((type_name, raw_source.strip(), added))

        output.append("".join(lines))

    output.append(dmb_text[pos:])

    log_lines = []
    log_lines.append("DMB slave texture duplication patch")
    log_lines.append("Targets: " + ", ".join(factions))
    log_lines.append("")
    for faction in factions:
        log_lines.append(f"{faction}: {len(units_by_faction[faction])} EDU units, {len(models_by_faction[faction])} DMB model refs")
        log_lines.append("  Units: " + ", ".join(units_by_faction[faction]))
        log_lines.append("  Models: " + ", ".join(sorted(models_by_faction[faction])))
        log_lines.append("")
    log_lines.append(f"Changed DMB blocks: {len(changes)}")
    for type_name, raw_source, added in changes:
        log_lines.append(f"{type_name}: added {', '.join(added)} from [{raw_source}]")
    if missing_types:
        log_lines.append("")
        log_lines.append("Missing DMB type refs from EDU/mount map:")
        log_lines.extend("  " + m for m in missing_types)

    return "".join(output), "\n".join(log_lines) + "\n", changes, missing_types


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DMB Slave Texture Duplicator")
        self.geometry("900x620")

        self.dmb_var = tk.StringVar()
        self.edu_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.factions_var = tk.StringVar(value=DEFAULT_FACTIONS)

        self._build()

    def _row(self, label, variable, browse_cmd, row):
        tk.Label(self, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        tk.Entry(self, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        tk.Button(self, text="Browse", command=browse_cmd).grid(row=row, column=2, padx=8, pady=6)

    def _build(self):
        self.columnconfigure(1, weight=1)
        self._row("descr_model_battle.txt", self.dmb_var, self.pick_dmb, 0)
        self._row("export_descr_unit.txt", self.edu_var, self.pick_edu, 1)
        self._row("Output DMB", self.out_var, self.pick_output, 2)

        tk.Label(self, text="Target factions", anchor="w").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        tk.Entry(self, textvariable=self.factions_var).grid(row=3, column=1, columnspan=2, sticky="ew", padx=8, pady=6)

        tk.Button(self, text="Patch DMB", command=self.run_patch, height=2).grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=8)

        self.log = scrolledtext.ScrolledText(self, wrap=tk.WORD)
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(5, weight=1)

    def pick_dmb(self):
        path = filedialog.askopenfilename(title="Select descr_model_battle.txt", filetypes=[("Text files", "*.txt"), ("All files", "*")])
        if path:
            self.dmb_var.set(path)
            if not self.out_var.get():
                p = Path(path)
                self.out_var.set(str(p.with_name(p.stem + "_patched" + p.suffix)))

    def pick_edu(self):
        path = filedialog.askopenfilename(title="Select export_descr_unit.txt", filetypes=[("Text files", "*.txt"), ("All files", "*")])
        if path:
            self.edu_var.set(path)

    def pick_output(self):
        path = filedialog.asksaveasfilename(title="Save patched DMB as", defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*")])
        if path:
            self.out_var.set(path)

    def run_patch(self):
        try:
            dmb_path = Path(self.dmb_var.get())
            edu_path = Path(self.edu_var.get())
            out_path = Path(self.out_var.get())
            factions = parse_factions(self.factions_var.get())

            if not dmb_path.is_file():
                raise FileNotFoundError("Choose a valid descr_model_battle.txt file.")
            if not edu_path.is_file():
                raise FileNotFoundError("Choose a valid export_descr_unit.txt file.")
            if not factions:
                raise ValueError("Enter at least one target faction.")

            patched, log_text, changes, missing = patch_dmb(
                dmb_path.read_text(errors="ignore"),
                edu_path.read_text(errors="ignore"),
                factions,
            )
            out_path.write_text(patched)
            log_path = out_path.with_suffix(out_path.suffix + ".log.txt")
            log_path.write_text(log_text)

            self.log.delete("1.0", tk.END)
            self.log.insert(tk.END, log_text)
            messagebox.showinfo("Done", f"Patched {len(changes)} DMB blocks.\n\nSaved:\n{out_path}\n{log_path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


if __name__ == "__main__":
    App().mainloop()
