import os
import re
import shutil
from PIL import Image
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QFileDialog, QVBoxLayout, QListWidget
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox

# -------------------------
# Logging
# -------------------------
import logging

logging.basicConfig(
    filename="rtw_importer.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def log(msg, level="info"):
    print(msg)

    if level == "error":
        logging.error(msg)
    else:
        logging.info(msg)


# -------------------------
# CONFIG
# -------------------------
UNIT_PREFIX = "my_mod"

# -------------------------
# PATH HELPERS
# -------------------------
def normalize_mod_path(path):
    return path.replace("\\", "/").rstrip("/")

def get_mod_dir_name(mod_path):
    return os.path.basename(normalize_mod_path(mod_path))

def get_unit_names_from_edu(path):
    units = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("type"):
                units.append(line.strip().split()[1])
    return units

# -------------------------
# PARSER: EDU
# -------------------------
def parse_edu(path):
    units = {}
    current = None
    buffer = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("type"):
                if current:
                    units[current] = "".join(buffer)
                current = line.strip().split()[1]
                buffer = [line]
            elif current:
                buffer.append(line)

        if current:
            units[current] = "".join(buffer)



    return units

def get_unit_ownership(edu_block):
    match = re.search(r"ownership\s+(.+)", edu_block)
    if not match:
        return []

    return match.group(1).strip().split()

    # return first faction (can expand later)

# -------------------------
# PARSER: MODEL_BATTLE
# -------------------------
def parse_model_battle(path):
    models = {}
    current = None
    buffer = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("type"):
                if current:
                    models[current] = "".join(buffer)
                current = line.strip().split()[1]
                buffer = [line]
            elif current:
                buffer.append(line)

        if current:
            models[current] = "".join(buffer)

    return models

# -------------------------
# PARSER: EXPORT_UNITS
# -------------------------
def parse_export_units(path):
    data = {}
    current = None
    buffer = []

    with open(path, "r", encoding="utf-16-le", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("unit"):
                if current:
                    data[current] = "".join(buffer)
                current = line.strip().split()[1]
                buffer = [line]
            elif current:
                buffer.append(line)

        if current:
            data[current] = "".join(buffer)

    return data

# -------------------------
# RENAME SYSTEM
# -------------------------
def rename_block(block, old_name, new_name):
    re.sub(rf"\b{re.escape(old_name)}\b", new_name, block)

def generate_new_name(name):
    return f"{UNIT_PREFIX}_{name}".lower()

def format_edb_name(name):
    return name.replace("_", " ")

# -------------------------
# STAT REBALANCE
# -------------------------
def rebalance_edu_block(block):
    block = re.sub(r"stat_pri\s+(\d+),", lambda m: f"stat_pri {min(int(m.group(1)), 10)},", block)
    block = re.sub(r"stat_sec\s+(\d+),", lambda m: f"stat_sec {min(int(m.group(1)), 8)},", block)
    block = re.sub(
        r"stat_armour\s+(\d+),\s*(\d+),\s*(\d+)",
        lambda m: f"stat_armour {min(int(m.group(1)), 10)}, {m.group(2)}, {m.group(3)}",
        block
    )
    return block

# -------------------------
# DMB ASSET EXTRACTION
# -------------------------
def extract_assets_from_dmb(block):
    assets = []
    assets += re.findall(r"texture\s+\w+,\s*([^\s]+)", block)
    assets += re.findall(r"model_flexi\s+([^\s,]+)", block)
    return assets

# -------------------------
# COPY ASSETS
# -------------------------
def copy_assets_from_list(asset_paths, src_mod, dst_mod):
    for path in asset_paths:
        if "data/" not in path:
            continue

        rel = path.split("data/")[-1]

        src = os.path.join(src_mod, "data", rel)
        dst = os.path.join(dst_mod, "data", rel)

        os.makedirs(os.path.dirname(dst), exist_ok=True)

        # try multiple extensions (RTW uses mixed formats)
        variants = [
            src,
            src.replace(".tga", ".dds"),
            src.replace(".dds", ".tga"),
        ]

        copied = False
        for v in variants:
            if os.path.exists(v):
                shutil.copy2(v, dst)
                log(f"[COPIED] {os.path.basename(v)}")
                copied = True
                break

        if not copied:
            log(f"[MISSING] {rel}", "error")

# -------------------------
# FIX MODEL_BATTLE PATHS
# -------------------------
def fix_model_battle(block, new_name, target_mod_dir, faction="slave"):
    block = re.sub(r"type\s+\S+", f"type {new_name}", block)

    def fix_texture(match):
        _old_faction = match.group(1)
        path = match.group(2)

        filename = os.path.basename(path)
        new_path = f"{target_mod_dir}/data/models_unit/textures/{filename}"

        return f"texture {faction}, {new_path}"

    block = re.sub(r"texture\s+(\w+),\s*([^\s]+)", fix_texture, block)

    def fix_model(match):
        path = match.group(1)
        num = match.group(2)

        filename = os.path.basename(path)
        new_path = f"{target_mod_dir}/data/models_unit/{filename}"

        return f"model_flexi {new_path}, {num}"

    block = re.sub(r"model_flexi\s+([^\s,]+),\s*(\d+)", fix_model, block)

    return block

# -------------------------
# WRITE BACK
# -------------------------
def append_to_file(path, content):
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n\n" + content)

# -------------------------
# BUILDINGS INTEGRATION
# -------------------------
def add_to_recruitment_all(eb_path, unit_name, faction):
    if not os.path.exists(eb_path):
        log("[EDB MISSING]", "error")
        return

    with open(eb_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    if unit_name in text:
        log(f"[EDB EXISTS] {unit_name}")
        return

    recruit_line = f'                recruit "{unit_name}"  0  requires factions {{ {faction}, }}\n'

    # target buildings
    buildings = ["barracks", "equestrian", "missiles"]

    def inject_into_capability(block):
        return re.sub(
            r"(capability\s*\{)",
            lambda m: m.group(1) + "\n" + recruit_line,
            block
        )

    # -------------------------
    # PROCESS EACH BUILDING BLOCK
    # -------------------------
    for b in buildings:
        pattern = rf"(building\s+{b}\s*\{{.*?\n\}})"
        
        def process_building(match):
            block = match.group(1)
            block = inject_into_capability(block)
            return block

        text = re.sub(pattern, process_building, text, flags=re.S)

    # -------------------------
    # WRITE BACK
    # -------------------------
    with open(eb_path, "w", encoding="utf-8") as f:
        f.write(text)

    log(f"[EDB ADDED ALL] {unit_name} -> barracks/equestrian/missiles")

# -------------------------
# FULL IMPORT
# -------------------------
def import_unit_full(unit_name, src_mod, dst_mod, faction="slave"):
    src_mod = normalize_mod_path(src_mod)
    dst_mod = normalize_mod_path(dst_mod)

    target_mod_dir = get_mod_dir_name(dst_mod)

    edu = parse_edu(f"{src_mod}/data/export_descr_units.txt")
    mb = parse_model_battle(f"{src_mod}/data/descr_model_battle.txt")
    eu = parse_export_units(f"{src_mod}/data/text/export_units.txt")

    if unit_name not in edu:
        raise Exception("Unit not found in EDU")

    new_name = generate_new_name(unit_name)

    # EDU
    edu_block = rename_block(edu[unit_name], unit_name, new_name)
    edu_block = rebalance_edu_block(edu_block)
    append_to_file(f"{dst_mod}/data/export_descr_units.txt", edu_block)

    edu_block_raw = edu[unit_name]

    detected_factions = get_unit_ownership(edu_block_raw)

    if detected_factions:
        faction = ", ".join(detected_factions)

    # MODEL BATTLE
    if unit_name in mb:
        mb_block = mb[unit_name]
        assets = []
        if unit_name in mb:
            assets = extract_assets_from_dmb(mb_block)

        mb_block = rename_block(mb_block, unit_name, new_name)
        mb_block = fix_model_battle(mb_block, new_name, target_mod_dir)

        append_to_file(f"{dst_mod}/data/descr_model_battle.txt", mb_block)
        copy_assets_from_list(assets, src_mod, dst_mod)

    # EXPORT UNITS
    if unit_name in eu:
        eu_block = rename_block(eu[unit_name], unit_name, new_name)
        append_to_file(f"{dst_mod}/data/text/export_units.txt", eu_block)

    # BUILDINGS
    add_to_recruitment_all(f"{dst_mod}/data/export_descr_buildings.txt", new_name, faction)

    # ADD THIS
    copy_and_rename_ui_assets(unit_name, new_name, src_mod, dst_mod)

    print(f"[DONE] {unit_name}")

# -------------------------
# BATCH IMPORT
# -------------------------
def batch_import(unit_list, src_mod, dst_mod):
    for unit in unit_list:
        try:
            import_unit_full(unit, src_mod, dst_mod)
        except Exception as e:
            print(f"[FAIL] {unit}: {e}")

def parse_descr_sm_factions(path):
    factions = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if line.startswith("faction"):
                # remove comments
                line = line.split(";")[0].strip()

                parts = line.split()
                if len(parts) >= 2:
                    factions.append(parts[1])

    return factions

def copy_and_rename_ui_assets(unit_name, new_name, src_mod, dst_mod):
    folders = [
        "data/ui/unit_cards",
        "data/ui/unit_info"
    ]

    old = unit_name.lower().replace(" ", "_")
    new = new_name.lower().replace(" ", "_")

    for folder in folders:
        src_dir = os.path.join(src_mod, folder)
        dst_dir = os.path.join(dst_mod, folder)

        if not os.path.exists(src_dir):
            continue

        os.makedirs(dst_dir, exist_ok=True)

        for f in os.listdir(src_dir):
            fl = f.lower()

            if (
                old in fl or
                fl.startswith("#" + old)
            ):
                src_file = os.path.join(src_dir, f)

                new_file = fl.replace(old, new)
                dst_file = os.path.join(dst_dir, new_file)

                shutil.copy2(src_file, dst_file)
                log(f"[UI COPIED] {new_file}")

# -------------------------
# UI: UNIT CARD VIEWER
# -------------------------
class UnitViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTW Unit Importer")

        self.layout = QVBoxLayout()

        self.list = QListWidget()
        self.list.itemClicked.connect(self.show_image)

        self.image = QLabel("Unit Card")
        self.image.setFixedHeight(256)

        self.load_btn = QPushButton("Load Unit Cards Folder")
        self.load_btn.clicked.connect(self.load_folder)

        self.layout.addWidget(self.load_btn)
        self.layout.addWidget(self.list)
        self.layout.addWidget(self.image)

        self.setLayout(self.layout)
        self.folder = None

    def load_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select unit card folder")
        if not folder:
            return

        self.folder = folder
        self.list.clear()

        for f in os.listdir(folder):
            if f.lower().endswith((".tga", ".png")):
                self.list.addItem(f)

    def show_image(self, item):
        path = os.path.join(self.folder, item.text())

        img = Image.open(path)
        img = img.convert("RGBA")
        img.save("temp_preview.png")

        pixmap = QPixmap("temp_preview.png")
        self.image.setPixmap(pixmap)

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QListWidget, QHBoxLayout, QTextEdit
)
from PySide6.QtCore import Qt

class RTWImporterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTW Unit Importer Pro")
        self.setAcceptDrops(True)

        self.src_mod = None
        self.dst_mod = None
        self.units_cache = []

        layout = QVBoxLayout()

        # --- MOD SELECT ---
        self.src_btn = QPushButton("Select SOURCE mod")
        self.src_btn.clicked.connect(self.select_src)

        self.dst_btn = QPushButton("Select TARGET mod")
        self.dst_btn.clicked.connect(self.select_dst)

        layout.addWidget(self.src_btn)
        layout.addWidget(self.dst_btn)

        # --- UNIT DROPDOWN ---
        self.unit_dropdown = QComboBox()
        layout.addWidget(self.unit_dropdown)

        self.add_btn = QPushButton("Add Unit")
        self.add_btn.clicked.connect(self.add_selected_unit)
        layout.addWidget(self.add_btn)

        # --- UNIT LIST ---
        self.unit_list = QListWidget()
        self.unit_list.setSelectionMode(QListWidget.SingleSelection)
        self.unit_list.setFocusPolicy(Qt.StrongFocus)
        self.unit_list.itemClicked.connect(self.preview_unit_card)
        layout.addWidget(self.unit_list)

        # --- IMAGE PREVIEW ---
        self.image = QLabel("Preview")
        self.image.setFixedHeight(200)
        layout.addWidget(self.image)

        # --- FACTION SELECT ---
        self.faction_dropdown = QComboBox()
        layout.addWidget(self.faction_dropdown)

        # --- IMPORT BUTTON ---
        self.import_btn = QPushButton("Import All")
        self.import_btn.clicked.connect(self.import_units)
        layout.addWidget(self.import_btn)

        # --- DMB PREVIEW ---
        self.dmb_preview = QTextEdit()
        layout.addWidget(self.dmb_preview)

        self.preview_btn = QPushButton("Preview DMB")
        self.preview_btn.clicked.connect(self.preview_dmb)
        layout.addWidget(self.preview_btn)

        # --- LOG ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)

    # -------------------------
    def load_factions(self):
        if not self.src_mod:
            return

        path = os.path.join(self.src_mod, "data/descr_sm_factions.txt")

        if not os.path.exists(path):
            self.log.append("[NO descr_sm_factions.txt]")
            return

        factions = parse_descr_sm_factions(path)

        self.faction_dropdown.clear()
        self.faction_dropdown.addItems(factions)

        self.log.append(f"[FACTIONS LOADED: {len(factions)}]")

    # -------------------------
    def select_src(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Mod")
        if not folder:
            return

        self.src_mod = folder

        edu_path = os.path.join(folder, "data/export_descr_units.txt")

        if os.path.exists(edu_path):
            self.units_cache = get_unit_names_from_edu(edu_path)

            self.unit_dropdown.clear()
            self.unit_dropdown.addItems(self.units_cache)
            self.unit_list.addItems(self.units_cache)

            self.load_factions()

            self.log.append(f"[LOADED {len(self.units_cache)} units]")

    # -------------------------
    def select_dst(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Mod")
        if folder:
            self.dst_mod = folder

    # -------------------------
    def add_selected_unit(self):
        unit = self.unit_dropdown.currentText()
        if unit:
            self.unit_list.addItem(unit)

    # -------------------------
    def import_units(self):
        if not self.src_mod or not self.dst_mod:
            self.log.append("[ERROR] Select both mods first")
            return

        units = [self.unit_list.item(i).text() for i in range(self.unit_list.count())]

        if not units:
            selected = self.unit_dropdown.currentText()
            if selected:
                units = [selected]

        for unit in units:
            try:
                import_unit_full(unit, self.src_mod, self.dst_mod)
                self.log.append(f"[OK] {unit}")
            except Exception as e:
                self.log.append(f"[FAIL] {unit}: {e}")

    # -------------------------
    def preview_dmb(self):
        if not self.src_mod:
            return

        unit = self.unit_dropdown.currentText()
        mb_path = os.path.join(self.src_mod, "data/descr_model_battle.txt")

        mb = parse_model_battle(mb_path)

        if unit in mb:
            self.dmb_preview.setText(mb[unit])

    # -------------------------
    def preview_unit_card(self, item):
        if not self.src_mod:
            return

        unit = item.text()
        card_dir = os.path.join(self.src_mod, "data/ui/unit_cards")

        if not os.path.exists(card_dir):
            return

        for f in os.listdir(card_dir):
            name = unit.lower().replace(" ", "_")

            if (
                name in f.lower() or
                f.lower().startswith("#" + name) or
                "unit_info" in f.lower()
            ):
                path = os.path.join(card_dir, f)

                img = Image.open(path).convert("RGBA")
                img.save("temp_preview.png")

                self.image.setPixmap(QPixmap("temp_preview.png"))
                break

    # -------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text()

        for line in text.splitlines():
            unit = line.strip()
            if unit:
                self.unit_list.addItem(unit)

if __name__ == "__main__":
    import sys

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = RTWImporterUI()
    window.showMaximized()

    sys.exit(app.exec())