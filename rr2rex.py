#!/usr/bin/env python3
"""
rr2rex - Rome Remastered to OG Rome Mod Converter v1.1

Converts mods made for Total War: Rome Remastered back to the original
Rome: Total War (.txt) format.

Now with intelligent .idx/.dat pack handling:
- Unpacks pack.idx/pack.dat and skeletons.idx/skeletons.dat
- Merges individual animation/skeleton files from the mod
- Repacks into complete packs for OG Rome compatibility

Usage:
    python rr2rex.py <remastered_mod_path> <output_og_path> [--txt-only] [--copy-skeletons]

Where:
    remastered_mod_path = Path to your Rome Remastered mod's data folder
    output_og_path = Path where the OG Rome compatible mod will be created
    --txt-only         = Skip all non-.txt files (only process text files)
    --copy-skeletons   = Copy skeletons.idx/dat directly instead of merging

Based on: https://wiki.twcenter.net/index.php?title=File_Differences_-_Rome_Remastered
          and Feral Interactive's documentation.
"""

import os
import sys
import shutil
import tempfile

__version__ = "1.1.0"

# Import idx/dat packer/unpacker functionality
try:
    import rtwx_idx
    HAS_IDX = True
except ImportError:
    HAS_IDX = False

# ============================================================================
# File classification
# ============================================================================

# Files that exist ONLY in Remastered - skip these entirely
REMASTERED_ONLY_FILES = frozenset({
    'chat_filter.san',
    'checksum_blacklist.txt',
    'data_controlled_features.json',
    'data_controlled_variables.json',
    'descr_battle_ai_personalities.txt',
    'descr_campaigns.txt',
    'descr_effects_siege_tower_collapse.txt',
    'descr_effects_torch_fire.txt',
    'descr_faction_groups.txt',
    'descr_fog_params.txt',
    'descr_font_db_zh_cn.txt',
    'descr_font_db_ru.txt',
    'descr_mission_modifiers.txt',
    'descr_model_battle_template.txt',
    'descr_model_strat_template.txt',
    'descr_names_feral.txt',
    'descr_names_lookup_feral.txt',
    'descr_prebattle_script.txt',
    'descr_quick_battle_locations.txt',
    'descr_riverbanks.txt',
    'descr_skeleton_feral_overrides.txt',
    'descr_sm_ambient_objects.txt',
    'descr_sm_faction_logos.txt',
    'descr_sm_factions_difficulty.json',
    'descr_sm_icon_models.txt',
    'descr_sm_major_events.txt',
    'descr_sm_resource_groups.txt',
    'descr_time_of_day.txt',
    'descr_unit_variation.txt',
    'do_not_invert_normal_texture_list.txt',
    'export_descr_advice_timing_feral.txt',
    'export_descr_prologue_feral.txt',
    'export_descr_prologue_enums_feral.txt',
    'feral_descr_ai_personality.txt',
    'feral_descr_grass_textures.txt',
    'feral_descr_grass_usage.txt',
    'feral_descr_portraits_variation.txt',
    'feral_descr_reputations_and_relations.txt',
    'feral_descr_tonemap_lut.txt',
    'feral_descr_truesky.txt',
    'ui_scaling_system_sprite_blacklist.txt',
    'ui_scaling_system_sprite_sheets.txt',
    'ui_scaling_system_stock_objects.txt',
    'ui_sprites_warmer_version.txt',
    'descr_diplomacy_comments.txt',
    'descr_namelists.txt',
    'feral_descr_movement_multipliers.txt',
})

# Remastered-only directory names to skip entirely
REMASTERED_ONLY_DIRS = frozenset({
    'animals',
    'characters',
    'feral_texture_sheets',
    'feral_textures',
    'original_overrides',
    'string_overrides',
    'ui_overrides',
    'toggles',
    'major_event_scripts',
})

# Binary file extensions to always copy as-is (no conversion needed)
# NOTE: .idx and .dat files have special handling elsewhere; they are listed
# here so the main loop won't try to text-convert them.
BINARY_EXT = frozenset({
    '.db', '.cas', '.tga', '.dds', '.jpg', '.jpeg', '.png', '.tif', '.tiff',
    '.bmp', '.wav', '.mp3', '.opus', '.ogv', '.wmv', '.avi', '.webm',
    '.mpg', '.mpeg', '.san', '.json', '.cfg', '.dat', '.pack', '.idx', '.spr',
    '.mesh', '.mtl', '.obj', '.fbx', '.blend', '.dae',
    '.ttf', '.otf', '.cuf',
})

# ============================================================================
# Helpers
# ============================================================================

def ai_personality_og(name: str) -> str:
    """'comfortable_caesar' -> 'comfortable caesar'"""
    return name.replace('_', ' ')


def animal_name_og(name: str) -> str:
    """Singular Remastered animal type back to plural OG."""
    m = {'wardog': 'wardogs', 'pig': 'pigs', 'hound': 'hound'}
    return m.get(name, name)


def write_file(path: str, lines: list[str]) -> None:
    """Write lines with Windows ANSI (cp1252) encoding and CRLF line endings."""
    with open(path, 'w', encoding='cp1252', errors='replace', newline='\r\n') as f:
        for line in lines:
            f.write(line + '\n')


def read_file(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return [l.rstrip('\n\r') for l in f.readlines()]


def get_faction_names(path: str) -> set[str]:
    """Extract faction names from descr_sm_factions.txt, supporting both JSON-like and flat formats."""
    factions = set()
    if not os.path.exists(path):
        return factions
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        try:
            with open(path, 'r', encoding='cp1252', errors='replace') as f:
                content = f.read()
        except Exception:
            return factions

    # Clean comments
    clean_lines = []
    for line in content.splitlines():
        line_clean = line.split(";;")[0].split(";")[0].strip()
        if line_clean:
            clean_lines.append(line_clean)
        else:
            clean_lines.append("")
    clean_text = "\n".join(clean_lines)

    # 1. Try to parse JSON-like format
    import re
    m = re.search(r'"factions"\s*:\s*\[', clean_text, re.DOTALL)
    if m:
        def find_block_end(txt: str, start: int) -> int:
            if start >= len(txt):
                return len(txt)
            open_ch = txt[start]
            close_ch = '}' if open_ch == '{' else ']'
            depth = 0
            i = start
            while i < len(txt):
                ch = txt[i]
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return i + 1
                elif ch == '"':
                    i += 1
                    while i < len(txt) and txt[i] != '"':
                        if txt[i] == '\\':
                            i += 1
                        i += 1
                i += 1
            return len(txt)

        bracket_start = clean_text.find('[', m.start())
        if bracket_start >= 0:
            bracket_end = find_block_end(clean_text, bracket_start)
            array_body = clean_text[bracket_start+1:bracket_end-1]
            idx = 0
            while idx < len(array_body):
                m_fac = re.search(r'"(\w+)"\s*:\s*\{', array_body[idx:])
                if not m_fac:
                    break
                fname = m_fac.group(1)
                factions.add(fname)
                brace_start = array_body.find("{", idx + m_fac.start())
                brace_end = find_block_end(array_body, brace_start)
                idx = brace_end

    # 2. Try to parse flat format
    for line in content.splitlines():
        line_clean = line.split(";;")[0].split(";")[0].strip()
        parts = line_clean.split()
        if len(parts) >= 2 and parts[0] == 'faction':
            factions.add(parts[1])

    return factions


# ============================================================================
# .idx/.dat pack handling (unpack, merge individual files, repack)
# ============================================================================

def find_remastered_asset_dirs(src: str):
    """
    Search for rr_pack and rr_skel folders relative to src, its parent, or cwd.
    """
    # 1. In the source folder (usually data/)
    rr_pack = os.path.join(src, 'rr_pack')
    rr_skel = os.path.join(src, 'rr_skel')
    if os.path.isdir(rr_pack) and os.path.isdir(rr_skel):
        return rr_pack, rr_skel
    
    # 2. In the parent of source folder
    parent = os.path.dirname(os.path.abspath(src))
    rr_pack = os.path.join(parent, 'rr_pack')
    rr_skel = os.path.join(parent, 'rr_skel')
    if os.path.isdir(rr_pack) and os.path.isdir(rr_skel):
        return rr_pack, rr_skel
        
    # 3. In current working directory
    rr_pack = os.path.join(os.getcwd(), 'rr_pack')
    rr_skel = os.path.join(os.getcwd(), 'rr_skel')
    if os.path.isdir(rr_pack) and os.path.isdir(rr_skel):
        return rr_pack, rr_skel
        
    return None, None


def _rebuild_idx_pack(pack_type: str, idx_path: str, dat_path: str,
                      src: str, dst_dir: str) -> bool:
    """
    Unpack an .idx/.dat pair, merge in individual files from rr_pack/rr_skel,
    merge the files.txt to preserve the items, then repack.
    """
    if not HAS_IDX:
        # Fallback: just copy as-is
        shutil.copy2(idx_path, dst_dir)
        shutil.copy2(dat_path, dst_dir)
        return True

    base_name = os.path.basename(idx_path).lower()
    print(f"  IDX REBUILD: {os.path.basename(idx_path).ljust(20)}", end='', flush=True)

    # Resolve rr_pack and rr_skel folders
    rr_pack_dir, rr_skel_dir = find_remastered_asset_dirs(src)
    if not rr_pack_dir or not rr_skel_dir:
        print("FAILED (could not find rr_pack or rr_skel)")
        # Fallback: copy as-is
        shutil.copy2(idx_path, dst_dir)
        shutil.copy2(dat_path, dst_dir)
        return False

    # Determine which source folder to merge based on pack_type
    if pack_type == 'ANIM.PACK':
        merge_source_dir = rr_pack_dir
    elif pack_type == 'SKEL.PACK':
        merge_source_dir = rr_skel_dir
    else:
        print(f"FAILED (unsupported pack type: {pack_type})")
        # Fallback: copy as-is
        shutil.copy2(idx_path, dst_dir)
        shutil.copy2(dat_path, dst_dir)
        return False

    try:
        # 1. Create temporary directory to unpack the original pack files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create pack reader and extract original packs into temp_dir
            pack = rtwx_idx.create_idx_file(pack_type, is_medieval=False)
            if not rtwx_idx._extract_pack(pack, idx_path, list_only=False, outdir=temp_dir):
                print("FAILED (extracting original pack failed)")
                # Fallback: copy as-is
                shutil.copy2(idx_path, dst_dir)
                shutil.copy2(dat_path, dst_dir)
                return False

            # 1b. Flatten all extracted files from the source pack to be directly under data/animations/
            temp_files_txt = os.path.join(temp_dir, 'files.txt')
            original_extracted = []
            if os.path.exists(temp_files_txt):
                with open(temp_files_txt, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_clean = line.strip().replace('\\', '/')
                        if line_clean:
                            original_extracted.append(line_clean)

            seen_extracted = set()
            flattened_extracted = []
            for path_str in original_extracted:
                scale_suffix = ""
                scale_idx = path_str.lower().rfind(';scale=')
                if scale_idx >= 0:
                    scale_suffix = path_str[scale_idx:]
                    disk_path_str = path_str[:scale_idx]
                else:
                    disk_path_str = path_str

                if os.path.isfile(disk_path_str):
                    base_name = os.path.basename(disk_path_str)
                    target_dir = os.path.join(temp_dir, 'data', 'animations')
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, base_name)
                    
                    if os.path.abspath(disk_path_str) != os.path.abspath(target_path):
                        if os.path.exists(target_path):
                            os.remove(target_path)
                        shutil.move(disk_path_str, target_path)

                    flat_p = target_path.replace('\\', '/') + scale_suffix
                    if flat_p not in seen_extracted:
                        seen_extracted.add(flat_p)
                        flattened_extracted.append(flat_p)

            if flattened_extracted:
                with open(temp_files_txt, 'w', encoding='utf-8') as f:
                    for p in flattened_extracted:
                        f.write(p + '\n')

            # 2. Add the contents of merge_source_dir (rr_pack or rr_skel) to temp_dir, skipping existing
            # Flatten to be directly under data/animations
            new_copied_paths = []
            for root, dirs, files in os.walk(merge_source_dir):
                for file in files:
                    if file.lower() == 'files.txt':
                        continue
                    
                    dest_file_path = os.path.join(temp_dir, 'data', 'animations', os.path.basename(file))

                    # Skip if already exists
                    if os.path.exists(dest_file_path):
                        continue

                    # Create directory structure in temp_dir if needed
                    os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                    shutil.copy2(os.path.join(root, file), dest_file_path)
                    new_copied_paths.append(dest_file_path.replace('\\', '/'))

            # 3. Merge files.txt to preserve the items (again skip if already exists)
            temp_files_txt = os.path.join(temp_dir, 'files.txt')

            # Read existing items in temp_dir/files.txt
            existing_items = set()
            if os.path.exists(temp_files_txt):
                with open(temp_files_txt, 'r', encoding='utf-8') as f:
                    for line in f:
                        cleaned = line.strip().replace('\\', '/')
                        if cleaned:
                            existing_items.add(cleaned)

            # Append the newly copied files to temp_dir/files.txt if they are not already there
            new_lines = []
            for p in new_copied_paths:
                if p in existing_items:
                    continue
                new_lines.append(p)
                existing_items.add(p)

            if new_lines:
                with open(temp_files_txt, 'a', encoding='utf-8') as f:
                    for line in new_lines:
                        f.write(line + '\n')

            # 4. Pack the temporary folder into a new pack.(idx/dat) or skeletons.(idx/dat)
            # and copy the generated pack files to the target folder (dst_dir)
            temp_out_idx = os.path.join(temp_dir, 'output.idx')
            temp_out_dat = os.path.join(temp_dir, 'output.dat')

            # Read back all lines from merged files.txt to get the file list for packing
            files_to_pack = []
            if os.path.exists(temp_files_txt):
                with open(temp_files_txt, 'r', encoding='utf-8') as f:
                    files_to_pack = [line.strip() for line in f if line.strip()]

            # Build the pack using _build_pack
            out_pack = rtwx_idx.create_idx_file(pack_type, is_medieval=False)
            if not rtwx_idx._build_pack(out_pack, temp_out_idx, files_to_pack,
                                       preserve_paths=False, keep_bslash=False):
                print("FAILED (packing failed)")
                # Fallback: copy as-is
                shutil.copy2(idx_path, dst_dir)
                shutil.copy2(dat_path, dst_dir)
                return False

            # Copy generated files to dst_dir
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(temp_out_idx, os.path.join(dst_dir, os.path.basename(idx_path)))
            shutil.copy2(temp_out_dat, os.path.join(dst_dir, os.path.basename(dat_path)))

        print("OK")
        return True

    except Exception as e:
        print(f"FAILED ({e})")
        # Fallback: copy as-is
        shutil.copy2(idx_path, dst_dir)
        shutil.copy2(dat_path, dst_dir)
        return False


# ============================================================================
# Individual file converters  (each gets a list[str] and returns list[str])
# ============================================================================

def conv_descr_character(lines):
    """Remove entire 'type merchant' block."""
    out, skip = [], False
    for l in lines:
        s = l.strip().lower()
        if s.startswith('type') and 'merchant' in s:
            skip = True
            continue
        if skip:
            if s.startswith('type'):
                skip = False
                out.append(l)
            continue
        out.append(l)
    return out


def conv_export_descr_unit(lines):
    """Remove Remastered-only EDU fields and rebalance block."""
    import re
    out, in_reb = [], False
    skip_attrs = {'voice_indexes', 'ethnicity', 'is_female',
                  'tattoo_color', 'hair_color', 'hair_style'}
    i = 0
    while i < len(lines):
        l = lines[i]
        s = l.strip()
        if not s:
            out.append(l)
            i += 1
            continue
        if s.startswith('rebalance_statblock'):
            in_reb = True
            i += 1
            continue
        if in_reb:
            if s.startswith('}'):
                in_reb = False
            i += 1
            continue

        # Check for soldiers block (e.g. "soldiers          50, 0, 1.6, 0.4, 1.7")
        m = re.match(r'^(\s*)soldiers(\s+)(.*)$', l)
        if m:
            indent = m.group(1)
            spacing = m.group(2)
            params = m.group(3)
            
            # Find the first soldier type inside the block
            j = i + 1
            brace_depth = 0
            first_soldier = None
            block_end_idx = -1
            
            while j < len(lines):
                jl = lines[j]
                if ';' in jl:
                    js_code = jl.split(';', 1)[0].strip()
                else:
                    js_code = jl.strip()
                
                is_brace_line = False
                for char in js_code:
                    if char == '{':
                        brace_depth += 1
                        is_brace_line = True
                    elif char == '}':
                        brace_depth -= 1
                        is_brace_line = True
                
                if not is_brace_line and js_code:
                    if brace_depth >= 2 and first_soldier is None:
                        first_soldier = js_code
                
                if brace_depth == 0 and is_brace_line:
                    block_end_idx = j
                    break
                j += 1
            
            if first_soldier is not None and block_end_idx != -1:
                # Successfully parsed block; replace with singular soldier
                out.append(f"{indent}soldier{spacing}{first_soldier}, {params}")
                i = block_end_idx + 1
                continue

        first = s.split(None, 1)[0]
        if first in skip_attrs:
            i += 1
            continue
        # animal types
        if s.startswith('animal_type'):
            parts = s.split(None, 1)
            if len(parts) == 2:
                parts[1] = animal_name_og(parts[1])
                l = parts[0] + '\t' + parts[1]
        out.append(l)
        i += 1
    return out


def conv_export_descr_buildings(lines):
    """Strip new condition keywords, remove icon lines, classification lines, dummy lines, and ai_destruction_hint lines."""
    bad = {'tavern_bonus', 'currency_fixed', 'remastered_only',
           'is_player', 'extra_recruitment_points', 'extra_construction_points',
           'agent_limit_settlement', 'is_toggled', 'major_event'}
    out = []
    for l in lines:
        stripped = l.strip()
        if stripped.startswith('icon') or stripped.startswith('classification') or stripped.startswith('dummy') or stripped.startswith('ai_destruction_hint'):
            continue
        if any(w in l for w in bad):
            continue
        out.append(l)
    return out


def conv_descr_sm_factions(lines):
    """Convert Remastered JSON-like descr_sm_factions.txt back to OG flat format."""
    import re

    def find_block_end(txt: str, start: int) -> int:
        """Given start at '{' or '[', return index of matching '}' or ']'."""
        if start >= len(txt):
            return len(txt)
        open_ch = txt[start]
        close_ch = '}' if open_ch == '{' else ']'
        depth = 0
        i = start
        while i < len(txt):
            ch = txt[i]
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i + 1
            elif ch == '"':
                # skip string content
                i += 1
                while i < len(txt) and txt[i] != '"':
                    if txt[i] == '\\':
                        i += 1
                    i += 1
            i += 1
        return len(txt)

    def get_val(body, key, default=''):
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*(?:"([^"]*)"|(\d+(?:\.\d+)?)|(true|false))', body)
        if m:
            return m.group(1) or m.group(2) or m.group(3) or default
        return default

    def get_obj(body, key):
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*(\{)', body)
        if not m:
            return ''
        start = m.start(1)
        end = find_block_end(body, start)
        return body[start:end]

    def get_rgb(body, key):
        # Match "key": [ r, g, b, ]
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,?\s*\]', body)
        if m:
            return m.group(1), m.group(2), m.group(3)
        return None

    def strip_data(path: str) -> str:
        path = path.strip()
        if path.lower().startswith("data/"):
            path = path[5:]
        if path.lower().startswith("data\\"):
            path = path[5:]
        return path.replace("\\", "/")

    # Preprocess to clean comments for structure matching
    clean_lines = []
    for line in lines:
        line_clean = line.split(";;")[0].split(";")[0].strip()
        if line_clean:
            clean_lines.append(line.split(";;")[0].split(";")[0])
        else:
            clean_lines.append("")
    clean_text = "\n".join(clean_lines)

    # Find factions array block
    m = re.search(r'"factions"\s*:\s*\[', clean_text, re.DOTALL)
    if not m:
        return lines # fallback

    bracket_start = clean_text.find('[', m.start())
    if bracket_start < 0:
        return lines
    bracket_end = find_block_end(clean_text, bracket_start)
    array_body = clean_text[bracket_start+1:bracket_end-1]

    idx = 0
    out_lines = []
    while idx < len(array_body):
        m_fac = re.search(r'"(\w+)"\s*:\s*\{', array_body[idx:])
        if not m_fac:
            break
        
        fname = m_fac.group(1)
        brace_start = array_body.find("{", idx + m_fac.start())
        brace_end = find_block_end(array_body, brace_start)
        fbody = array_body[brace_start:brace_end]
        idx = brace_end

        culture = get_val(fbody, "culture", "roman")
        
        logos = get_obj(fbody, "logos")
        strat_symbol_model = get_val(logos, "strat symbol model")
        strat_rebel_symbol_model = get_val(logos, "strat rebel symbol model")
        loading_screen_icon = get_val(logos, "loading screen icon")
        standard_idx_val = get_val(logos, "standard index", "0")
        logo_idx_val = get_val(logos, "logo index", "0")
        rebel_logo_idx_val = get_val(logos, "rebel logo index", "20")

        colours = get_obj(fbody, "colours")
        primary_rgb = get_rgb(colours, "primary")
        secondary_rgb = get_rgb(colours, "secondary")

        movies = get_obj(fbody, "movies")
        intro_movie_path = get_val(movies, "intro")
        victory_movie_path = get_val(movies, "victory")
        defeat_movie_path = get_val(movies, "defeat")

        custom_battle = get_val(fbody, "available in custom battles", "true")
        prefer_naval = get_val(fbody, "prefer naval invasions", "false")

        # Process paths
        symbol_path = strip_data(strat_symbol_model)
        rebel_symbol_path = strip_data(strat_rebel_symbol_model)
        symbol_path = re.sub(r'symbol_romans_(\w+)\.CAS', r'symbol_\1.CAS', symbol_path, flags=re.IGNORECASE)
        rebel_symbol_path = re.sub(r'symbol_romans_(\w+)\.CAS', r'symbol_\1.CAS', rebel_symbol_path, flags=re.IGNORECASE)

        if primary_rgb:
            primary_str = f"red {primary_rgb[0]}, green {primary_rgb[1]}, blue {primary_rgb[2]}"
        else:
            primary_str = "red 0, green 0, blue 0"
            
        if secondary_rgb:
            secondary_str = f"red {secondary_rgb[0]}, green {secondary_rgb[1]}, blue {secondary_rgb[2]}"
        else:
            secondary_str = "red 0, green 0, blue 0"

        loading_icon_path = strip_data(loading_screen_icon)
        base_name = loading_icon_path.split("/")[-1].replace(".tga", "")
        if base_name.startswith("romans_"):
            base_name = base_name[7:]
        loading_logo_path = f"loading_screen/symbols/symbol128_{base_name}.tga"

        # Standard, Logo, Small indices directly from Logos block
        std_idx = standard_idx_val
        logo_idx = logo_idx_val
        small_logo_idx = rebel_logo_idx_val

        # Movies
        intro_path = strip_data(intro_movie_path)
        if intro_path.endswith("_1080p.wmv"):
            if fname in ('romans_julii', 'romans_scipii'):
                intro_path = intro_path.replace("_1080p.wmv", "_final.wmv")
            else:
                intro_path = intro_path.replace("_1080p.wmv", "_640x480_bars.wmv")

        victory_path = strip_data(victory_movie_path)
        if victory_path and not victory_path.endswith("_320x240.wmv") and victory_path.endswith(".wmv"):
            victory_path = victory_path.replace(".wmv", "_320x240.wmv")

        defeat_path = strip_data(defeat_movie_path)

        # Dynamic death movie
        stripped_name = fname[7:] if fname.startswith("romans_") else fname
        if stripped_name == "slave":
            stripped_name = "rebels"
        if culture in ('egyptian', 'eastern', 'carthaginian', 'desert'):
            climate = "sand"
        elif culture in ('barbarian', 'nomad'):
            climate = "snow"
        else:
            climate = "grass"
        death_path = f"fmv/death/death_{stripped_name}_{climate}_320x240.wmv"

        if culture in ('barbarian', 'nomad'):
            sap_val = "no"
        else:
            sap_val = "yes"

        custom_battle_val = "yes" if custom_battle == "true" else "no"
        prefer_naval_val = "yes" if prefer_naval == "true" else "no"

        out_lines.append(f"faction						{fname}")
        out_lines.append(f"culture						{culture}")
        out_lines.append(f"symbol						{symbol_path}")
        out_lines.append(f"rebel_symbol				{rebel_symbol_path}")
        out_lines.append(f"primary_colour				{primary_str}")
        out_lines.append(f"secondary_colour			{secondary_str}")
        out_lines.append(f"loading_logo				{loading_logo_path}")
        out_lines.append(f"standard_index				{std_idx}")
        out_lines.append(f"logo_index					{logo_idx}")
        out_lines.append(f"small_logo_index			{small_logo_idx}")
        out_lines.append(f"triumph_value				5")
        out_lines.append(f"intro_movie					{intro_path}")
        out_lines.append(f"victory_movie				{victory_path}")
        out_lines.append(f"defeat_movie				{defeat_path}")
        out_lines.append(f"death_movie					{death_path}")
        out_lines.append(f"custom_battle_availability	{custom_battle_val}")
        out_lines.append(f"can_sap						{sap_val}")
        out_lines.append(f"prefers_naval_invasions		{prefer_naval_val}")
        out_lines.append(";;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n")

    return out_lines


def conv_descr_sm_resources(lines):
    """Pass-through – vastly different format, can't auto-convert safely."""
    return lines


def conv_descr_strat(lines):
    """personality underscore fix + strip resource quantity + strip quantity flags."""
    import re
    out = []
    for l in lines:
        # Remove any occurrence of resource_quantity_enabled and resource_quantity_disabled strings
        l = l.replace('resource_quantity_enabled', '').replace('resource_quantity_disabled', '')
        
        s = l.strip()
        if s.startswith('personality '):
            parts = s.split(None, 2)
            parts[1] = ai_personality_og(parts[1])
            l = l[:len(l)-len(l.lstrip())] + ' '.join(parts)
            s = l.strip()
            
        if re.match(r'^resource\b', s):
            # Isolate comment
            comment = ""
            code_part = l
            if ';' in l:
                code_part, comment = l.split(';', 1)
                comment = ';' + comment
            
            # Match prefix, resource name, quantity, x, y
            m = re.match(r'^(\s*resource\s+)([^,]+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$', code_part)
            if m:
                prefix = m.group(1)
                res_name = m.group(2).strip()
                x_coord = m.group(4)
                y_coord = m.group(5)
                l = f"{prefix}{res_name}, {x_coord}, {y_coord}{comment}"
                
        out.append(l)
    return out


def conv_descr_win_conditions(lines):
    """Add warning about settlement vs region name change."""
    warn = (";\n; NOTE: Remastered uses settlement names in hold_regions;\n"
            " OG Rome requires region names. Verify descr_regions.txt!\n;\n")
    ins = 0
    for i, l in enumerate(lines):
        if not l.startswith(';') and l.strip():
            ins = i
            break
    result = lines[:]
    for w in reversed(warn.split('\n')):
        result.insert(ins, w)
    return result


def conv_descr_aerial_map_bases(lines):
    """Drop 'size' lines."""
    return [l for l in lines if not l.strip().startswith('size ')]


def conv_descr_animals(lines):
    """Drop 'width' and 'offset' lines."""
    result = []
    for l in lines:
        s = l.strip()
        if s.startswith('class'):
            l = l.replace('hound', 'wardog')
        if not s:
            result.append(l)
            continue
        if s.split(None, 1)[0] in ('width', 'offset'):
            continue
        result.append(l)
    return result


def conv_descr_climates(lines):
    """Drop new Remastered climate attributes."""
    bad = {'dust_color', 'mud_color', 'mountain', 'coarse_detail', 'far_coarse_detail'}
    return [l for l in lines if not any(l.strip().startswith(b) for b in bad)]


def conv_descr_cultures(lines):
    """
    Convert Remastered JSON-like descr_cultures.txt back to OG flat format.
    
    Remastered format is JSON-like (since v2.0):
        "cultures": [ { "roman": { "string": "ROMAN", ... } }, ... ]
    
    OG format is flat:
        culture roman
        portrait_mapping roman
        rebel_standard_index 0
        { ... settlement blocks ... }
        fort ...CAS, fort_roman
        watchtower ...CAS, watchtower_roman
        spy ...tga ...tga ...tga cost p r
        assassin ...
        diplomat ...
        admiral ...
    
    We can only extract what the Remastered file provides. Settlement model
    paths are now stored in settlement plan files, so we generate reasonable
    defaults for those.
    """
    import re

    def find_block_end(txt: str, start: int) -> int:
        """Given start at '{' or '[', return index of matching '}' or ']'."""
        if start >= len(txt):
            return len(txt)
        open_ch = txt[start]
        close_ch = '}' if open_ch == '{' else ']'
        depth = 0
        i = start
        while i < len(txt):
            ch = txt[i]
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i + 1
            elif ch == '"':
                # skip string content
                i += 1
                while i < len(txt) and txt[i] != '"':
                    if txt[i] == '\\':
                        i += 1
                    i += 1
            i += 1
        return len(txt)

    # 1. Strip comment-only lines (;;)
    clean = []
    for l in lines:
        s = l.strip()
        if s.startswith(';;'):
            clean.append('')
        else:
            clean.append(l)
    text = '\n'.join(clean)

    # 2. Find the cultures array body
    m = re.search(r'"cultures":\s*\[', text, re.DOTALL)
    if not m:
        return lines  # fallback
    bracket_start = text.find('[', m.start())
    if bracket_start < 0:
        return lines
    bracket_end = find_block_end(text, bracket_start)
    if bracket_end <= bracket_start + 2:
        return lines
    array_body = text[bracket_start+1:bracket_end-1]

    # 3. Split top-level culture objects: "name": { ... },
    # Build by matching braces depth-first
    idx = 0
    culture_blocks = []
    while idx < len(array_body):
        # skip whitespace/comma
        while idx < len(array_body) and array_body[idx] in ',\n\r\t ':
            idx += 1
        if idx >= len(array_body):
            break
        # match "name": {
        name_match = re.match(r'"(\w+)"\s*:\s*\{', array_body[idx:])
        if not name_match:
            idx += 1
            continue
        cname = name_match.group(1)
        block_start = idx + name_match.end() - 1  # position of {
        block_end = find_block_end(array_body, block_start)
        cbody = array_body[block_start:block_end]
        culture_blocks.append((cname, cbody))
        idx = block_end

    REBEL_INDEX = {
        'roman': 0, 'barbarian': 1, 'carthaginian': 2,
        'eastern': 3, 'greek': 4, 'egyptian': 5,
    }

    def get_val(body, key, default=''):
        """Extract a simple quoted value: "key": "value" or "key": number or "key": true/false"""
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*(?:"([^"]*)"|(\d+(?:\.\d+)?)|(true|false))', body)
        if m:
            return m.group(1) or m.group(2) or m.group(3) or default
        return default

    def get_obj(body, key):
        """Extract a nested {} block: "key": { ... }"""
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*(\{)', body)
        if not m:
            return ''
        start = m.start(1)
        depth = 0
        i = start
        while i < len(body):
            if body[i] == '{':
                depth += 1
            elif body[i] == '}':
                depth -= 1
                if depth == 0:
                    return body[start:i+1]
            i += 1
        return ''

    def get_agents(body):
        """Parse the agents block into a dict of agent_type -> {field: value}"""
        agents = {}
        ag = get_obj(body, 'agents')
        if not ag:
            return agents
        # Each agent: "spy": { "info card": "x", ... },
        for m in re.finditer(r'"(\w+)":\s*\{([^}]*)\}', ag):
            aname, abody = m.group(1), m.group(2)
            info = {}
            for kv in re.finditer(r'"([^"]+)"\s*:\s*(?:"([^"]*)"|(\d+))', abody):
                info[kv.group(1)] = kv.group(2) or kv.group(3)
            agents[aname] = info
        return agents

    def get_icons(body):
        """Extract settlement icon paths."""
        icons = {}
        ib = get_obj(body, 'settlement icons')
        if ib:
            for m in re.finditer(r'"(\w+)"\s*:\s*"([^"]*)"', ib):
                icons[m.group(1)] = m.group(2)
        return icons

    out = []
    # Header
    out.append("symbol\tdata/models_strat/residences/symbol.CAS")
    out.append("siege\tdata/models_strat/residences/siege_icon.CAS")
    out.append("")
    out.append("blockade\t\tdata/models_strat/residences/blockade_icon.CAS")
    out.append("")

    for cname, cbody in culture_blocks:
        portrait = get_val(cbody, 'portrait mapping', cname)
        rebel = REBEL_INDEX.get(cname, 0)
        max_lvl = get_val(cbody, 'max settlement level', 'huge_city')

        out.append(f"culture\t\t\t\t{cname}")
        out.append(f"portrait_mapping\t{portrait}")
        out.append(f"rebel_standard_index\t{rebel}")
        out.append("{")

        levels = ['village', 'town', 'large_town', 'city', 'large_city', 'huge_city']
        if max_lvl in levels:
            levels = levels[:levels.index(max_lvl) + 1]

        icons = get_icons(cbody)
        for lvl in levels:
            icon = icons.get(lvl, f'data/ui/{cname}/cities/{cname}_{lvl}.tga')
            lvl_idx = levels.index(lvl) + 1
            out.append(f"{lvl}")
            out.append("{")
            out.append(f"\tnormal\t\t\tdata/models_strat/residences/{cname}_{lvl}_buildings.CAS,\t\tsettlement_{cname}_level_{lvl_idx}")
            # Wall entries for levels town and above
            if lvl != 'village':
                # OG usually has 3-5 wall entries depending on level
                num_walls = 3
                if lvl in ('city', 'large_city', 'huge_city'):
                    num_walls = {'city': 4, 'large_city': 4, 'huge_city': 5}.get(lvl, 4)
                for w in range(1, num_walls + 1):
                    out.append(f"\twall\t\t\t\tdata/models_strat/residences/{cname}_{lvl}_wall_{w}.CAS,\t\tsettlement_{cname}_walled_level_{lvl_idx}")
            out.append(f"\tcard\t\t\t\t{icon}")
            out.append("}")

        out.append("}")

        # Fort
        fort_body = get_obj(cbody, 'fort')
        fc = get_val(fort_body, 'cost', '500')
        out.append(f"fort\t\t\t\tdata/models_strat/residences/{cname}_fort.CAS,\t\t\t\t\t\tfort_{cname}")
        out.append(f"fort_cost\t\t\t{fc}")
        out.append(f"fort_wall\t\t\tdata/models_strat/residences/{cname}_fort_wall.CAS")

        # Ports (generic - modders need to adjust)
        for i, lvl in enumerate(['fishing_village', 'port_land', 'port_land', 'port_land']):
            if i == 0:
                out.append(f"{lvl}\t\tdata/models_strat/residences/{cname}_fishing_village.CAS,\t\t\t\tport_{cname}_level_1")
            else:
                n = ['', '_01', '_02', '_03'][i]
                out.append(f"{lvl}\t\t\tdata/models_strat/residences/{cname}_port{n}_land.CAS,\t\t\t\tport_{cname}_level_{i+1}")
                out.append(f"port_sea\t\t\tdata/models_strat/residences/{cname}_port{n}_sea.CAS")

        # Watchtower
        wt_body = get_obj(cbody, 'watchtower')
        wt_cost = get_val(wt_body, 'cost', '200')
        wt_model = get_val(wt_body, 'base model', f'data/models_strat/residences/watchtower_{cname}.CAS')
        wt_base = get_val(wt_body, 'aerial map base', f'watchtower_{cname}')
        out.append(f"watchtower\t\t\t{wt_model},\t\t\t\t\t{wt_base}")
        out.append(f"watchtower_cost\t\t{wt_cost}")

        # Agents
        agents = get_agents(cbody)
        defaults = {
            'spy': ('spy.tga', 'spy_info.tga', '350', '1', '1'),
            'assassin': ('assassin.tga', 'assassin_info.tga', '500', '1', '1'),
            'diplomat': ('diplomat.tga', 'diplomat_info.tga', '250', '1', '1'),
            'merchant': ('merchant.tga', 'merchant_info.tga', '250', '1', '1'),
            'admiral': ('admiral.tga', 'admiral_info.tga', '100', '1', '1'),
        }
        for atype in ['spy', 'assassin', 'diplomat', 'admiral']:
            info = agents.get(atype, {})
            uc = info.get('unit card', defaults[atype][0])
            ic = info.get('info card', defaults[atype][1])
            cost = info.get('recruitment cost', defaults[atype][2])
            pc = info.get('population cost', defaults[atype][3])
            rp = info.get('recruitment points', defaults[atype][4])
            out.append(f"{atype}\t\t\t{uc}\t\t\t{ic}\t\t\t{uc}\t\t\t{cost}\t{pc}\t{rp}")

        # Separator
        out.append(";;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;")
        out.append("")

    return out


def conv_descr_cursor_actions(lines):
    """Remove merchant block."""
    out, skip = [], False
    for l in lines:
        s = l.strip().lower()
        if s.startswith('type') and 'merchant' in s:
            skip = True
            continue
        if skip:
            if s.startswith('type'):
                skip = False
                out.append(l)
            continue
        out.append(l)
    return out


def conv_descr_custom_locations(lines):
    """Drop 'sandstorm' lines."""
    return [l for l in lines if not l.strip().startswith('sandstorm')]


def conv_descr_daytypes(lines):
    """Drop grunge and sand_storm."""
    return [l for l in lines
            if not l.strip().startswith('grunge') and 'sand_storm' not in l]


def conv_descr_engines(lines):
    """Drop engine_outline, collapse_effect, arrow_tower, ballista_tower."""
    bad_starts = {'engine_outline', 'collapse_effect'}
    out = []
    for l in lines:
        s = l.strip()
        if any(s.startswith(b) for b in bad_starts):
            continue
        if 'arrow_tower' in s or 'ballista_tower' in s:
            continue
        out.append(l)
    return out


def conv_descr_event_enums(lines):
    """Drop new merchant events and new font names."""
    bad_events = {
        'new_merchant_acquired', 'merchant_mission_buyout',
        'merchant_mission_buyout_failed', 'merchant_mission_buyout_failed_acquired',
        'enemy_merchant_mission_buyout', 'enemy_merchant_mission_buyout_failed',
        'enemy_merchant_mission_buyout_failed_acquired',
        'army_retreating_ally', 'army_retreating_enemy',
        # Barbarian Expansion events not present in OG Rome
        'character_joins_through_rebellion',
        'character_rebels',
        'city_gained_through_revolt',
        'disaster_report',
        'huns_hording',
        'rebel_revolt_surpressed',
        'script_prompt',
    }
    bad_fonts = {'cinzel_med', 'verdana_med_bold', 'dark_brown'}
    return [l for l in lines
            if not any(e in l for e in bad_events)
            and not any(f in l for f in bad_fonts)]


def conv_descr_event_images(lines):
    """Remove entire event blocks for Remastered-only events, and strip bad fonts."""
    bad_events = {
        'new_merchant_acquired', 'merchant_mission_buyout',
        'merchant_mission_buyout_failed', 'merchant_mission_buyout_failed_acquired',
        'enemy_merchant_mission_buyout', 'enemy_merchant_mission_buyout_failed',
        'enemy_merchant_mission_buyout_failed_acquired',
        'army_retreating_ally', 'army_retreating_enemy',
        # Barbarian Expansion events not present in OG Rome
        'character_joins_through_rebellion',
        'settlement_razed',
        'character_rebels',
        'city_gained_through_revolt',
        'disaster_report',
        'huns_hording',
        'rebel_revolt_surpressed',
        'script_prompt',
        'rebels_victorious',
    }
    bad_fonts = {'cinzel_med', 'verdana_med_bold', 'dark_brown'}
    out, skip = [], False
    for l in lines:
        s = l.strip()
        # Line that starts a new event: at column 0, not comment, not empty,
        # not '{', '}', or 'format' (which are part of the current event's body)
        is_new_event = (len(l) > 0 and not l[0].isspace()
                        and not s.startswith(';') and s != ''
                        and s != '}' and s != '{' and s != 'format')
        
        if is_new_event and s in bad_events:
            skip = True
            continue
        
        if skip:
            if is_new_event:
                skip = False
                out.append(l)
            continue
        
        # Filter bad fonts from kept lines
        if any(f in l for f in bad_fonts):
            continue
        
        out.append(l)
    return out


def conv_descr_mount(lines):
    """Drop water_trail_effect_running."""
    return [l for l in lines if not l.strip().startswith('water_trail_effect_running')]


def conv_descr_particle(lines):
    """Drop new attrs and new particle types (grunge, sand, grass)."""
    bad_attr = {'normal_map', 'shading', 'friction', 'friction_horizontal'}
    skip_types = {'grunge', 'sand', 'grass'}
    out, skipping = [], False
    for l in lines:
        s = l.strip()
        if s.startswith('type ') and s.split(None, 1)[1] in skip_types:
            skipping = True
            continue
        if skipping:
            if s.startswith('type '):
                skipping = False
                out.append(l)
            continue
        if any(s.startswith(a) for a in bad_attr):
            continue
        out.append(l)
    return out


def conv_descr_projectile_new(lines):
    """Drop min_velocity, never_high, and javelin_with_pilum_skin block."""
    out, skipping = [], False
    for l in lines:
        s = l.strip()
        if l.startswith('display'):
            l = l.replace('thrown_weapon', '')
        if s.startswith('type') and 'javelin_with_pilum_skin' in s:
            skipping = True
            continue
        if skipping:
            if s.startswith('type'):
                skipping = False
                out.append(l)
            continue
        if s.startswith('min_velocity'):
            continue
        if s.startswith('never_high'):
            continue
        out.append(l)
    return out


def conv_descr_strat_sundries(lines):
    """Drop resource_hover / watch_tower_hover type blocks."""
    out, skipping = [], False
    bad_types = {'resource_hover', 'watch_tower_hover'}
    for l in lines:
        s = l.strip()
        if s.startswith('type ') and any(b in s for b in bad_types):
            skipping = True
            continue
        if skipping:
            if s.startswith('type '):
                skipping = False
                out.append(l)
            continue
        out.append(l)
    return out


def conv_export_descr_advice(lines):
    """Drop Manual attribute and new condition names."""
    bad_conds = {
        'SettlementHasDamagedBuilding', 'I_IsTutorialEnabled',
        'LocalPlayerHasReinforcements', 'LocalPlayerHasAIReinforcements',
        'LocalPlayerHasManualReinforcements', 'LocalPlayerBattlesFought',
    }
    result = []
    for l in lines:
        s = l.strip()
        if not s:
            result.append(l)
            continue
        if s.startswith('Manual'):
            continue
        if s.split(None, 1)[0] in bad_conds:
            continue
        result.append(l)
    return result


def conv_export_descr_character_traits(lines):
    """Drop new trait conditions & effects."""
    bad = {
        'Toggled', 'RemasteredEducation', 'NightBattlesEnabled',
        'RegionTradingResource', 'PreciousMineCount', 'TradingGroup',
        'IsFromFaction', 'HomeSettlementBuildingExists',
        'SettlementMerchantTradingWith', 'Finance', 'Conditional',
        'ElephantCommand', 'Lose', 'RemoveAncillary',
        'AcquisitionMission', 'SufferAcquisitionAttempt',
    }
    result = []
    for l in lines:
        s = l.strip()
        if not s:
            result.append(l)
            continue
        if s.split(None, 1)[0] in bad:
            continue
        result.append(l)
    return result


def conv_export_descr_ancillaries(lines):
    return conv_export_descr_character_traits(lines)


def conv_descr_model_battle(lines):
    """
    Remastered DMB has radically different format:
      - New: male, body, angry_face, medieval_features, tired, aged, pbr_texture
      - 'model <ethnicity> <path>'  (no .cas extension, no distance, no LOD)
      - 'no_variation model ...'
      - NO model_flexi, indiv_range, model_sprite, model_tri
    OG format requires: model_flexi/m with full .cas names + distances + sprite/tri.
    We generate approximate model_flexi entries and warn the user.
    """
    out = []
    out.append("; AUTO-CONVERTED FROM ROME REMASTERED DMB – VERIFY PATHS!")
    out.append(";")
    skip_attrs = {'male', 'female', 'body', 'angry_face', 'medieval_features',
                  'tired', 'aged', 'pbr_texture', 'no_variation'}
    in_type = False

    for l in lines:
        s = l.strip()
        first = s.split(None, 1)[0] if s else ''

        if s.startswith('type '):
            in_type = True
            out.append(l)
            continue
        if not in_type:
            out.append(l)
            continue

        # skip new Remastered attributes
        if first in skip_attrs:
            continue
        # skip no_variation lines
        if first == 'no_variation':
            continue

        # convert 'model' to 'model_flexi_m' with LOD entries
        if first == 'model':
            parts = s.split(None, 2)
            if len(parts) == 3:
                indent = l[:len(l)-len(l.lstrip())]
                p = parts[2]  # path without .cas
                out.append(f"{indent}model_flexi_m\t\t{p}_lod0.cas, 8")
                out.append(f"{indent}model_flexi_m\t\t{p}_lod0.cas, 15")
                out.append(f"{indent}model_flexi\t\t{p}_lod1.cas, 30")
                out.append(f"{indent}model_flexi\t\t{p}_lod2.cas, max")
                base = os.path.basename(p)
                out.append(f"{indent}model_sprite\t\t60.0, data/sprites/{base}.spr")
                out.append(f"{indent}model_tri\t\t400, 0.5f, 0.5f, 0.5f")
            else:
                out.append(l)
        elif first == 'skeleton':
            # Keep skeleton line, insert indiv_range after it
            out.append(l)
            out.append(f"{l[:len(l)-len(l.lstrip())]}indiv_range\t\t40")
        else:
            out.append(l)

    return out


def conv_descr_model_strat(lines):
    """Same approach as DMB for strat models."""
    out = []
    out.append("; AUTO-CONVERTED FROM ROME REMASTERED DMS – VERIFY PATHS!")
    out.append(";")
    skip_attrs = {'male', 'female', 'body', 'angry_face', 'medieval_features',
                  'tired', 'aged', 'pbr_texture', 'no_variation'}
    in_type = False

    for l in lines:
        s = l.strip()
        first = s.split(None, 1)[0] if s else ''

        if s.startswith('type '):
            in_type = True
            out.append(l)
            continue
        if not in_type:
            out.append(l)
            continue

        if first in skip_attrs:
            continue
        if first == 'no_variation':
            continue

        if first == 'model':
            parts = s.split(None, 2)
            if len(parts) == 3:
                indent = l[:len(l)-len(l.lstrip())]
                p = parts[2]
                out.append(f"{indent}model_flexi_m\t\t{p}_lod0.cas, 8")
                out.append(f"{indent}model_flexi_m\t\t{p}_lod0.cas, 15")
                out.append(f"{indent}model_flexi\t\t{p}_lod1.cas, 30")
                out.append(f"{indent}model_flexi\t\t{p}_lod2.cas, max")
            else:
                out.append(l)
        else:
            out.append(l)

    return out


def conv_settlement_plan(lines: list[str]) -> list[str]:
    """Remove the strat portion and its body but leave the rest."""
    import re
    out = []
    i = 0
    in_strat = False
    brace_depth = 0
    
    while i < len(lines):
        line = lines[i]
        line = re.sub(r'ten([ae])ment([a-eA-E])\d+', r'ten\1ment\2', line)
        clean_line = line.split(';', 1)[0].split('//', 1)[0].strip()
        
        if not in_strat:
            tokens = clean_line.split()
            if 'strat' in tokens:
                in_strat = True
                brace_depth = clean_line.count('{') - clean_line.count('}')
                i += 1
                continue
            else:
                out.append(line)
                i += 1
                continue
        else:
            if brace_depth == 0:
                if '{' in clean_line:
                    brace_depth += clean_line.count('{') - clean_line.count('}')
                i += 1
                continue
            else:
                brace_depth += clean_line.count('{') - clean_line.count('}')
                if brace_depth <= 0:
                    in_strat = False
                i += 1
                continue
                
    return out


# ============================================================================
# Converter registry – maps filename_lowercase -> converter function
# ============================================================================

CONVERTERS = {
    'descr_character.txt': conv_descr_character,
    'export_descr_unit.txt': conv_export_descr_unit,
    'export_descr_buildings.txt': conv_export_descr_buildings,
    'descr_sm_factions.txt': conv_descr_sm_factions,
    'descr_sm_resources.txt': conv_descr_sm_resources,
    'descr_strat.txt': conv_descr_strat,
    'descr_win_conditions.txt': conv_descr_win_conditions,
    'descr_aerial_map_bases.txt': conv_descr_aerial_map_bases,
    'descr_animals.txt': conv_descr_animals,
    'descr_climates.txt': conv_descr_climates,
    'descr_cultures.txt': conv_descr_cultures,
    'descr_cursor_actions.txt': conv_descr_cursor_actions,
    'descr_custom_locations.txt': conv_descr_custom_locations,
    'descr_daytypes.txt': conv_descr_daytypes,
    'descr_engines.txt': conv_descr_engines,
    'descr_event_enums.txt': conv_descr_event_enums,
    'descr_event_images.txt': conv_descr_event_images,
    'descr_mount.txt': conv_descr_mount,
    'descr_particle.txt': conv_descr_particle,
    'descr_projectile_new.txt': conv_descr_projectile_new,
    'descr_strat_sundries.txt': conv_descr_strat_sundries,
    'export_descr_advice.txt': conv_export_descr_advice,
    'export_descr_character_traits.txt': conv_export_descr_character_traits,
    'export_descr_ancillaries.txt': conv_export_descr_ancillaries,
    'descr_model_battle.txt': conv_descr_model_battle,
    'descr_model_strat.txt': conv_descr_model_strat,
}

# ============================================================================
# Known .idx/.dat pack files that need special handling
# ============================================================================

# Files that are animation/skeleton packs we should rebuild
# Maps idx filename -> (pack_type_magic, merge_source_relative_dir)
IDX_PACKS_TO_REBUILD = {
    'pack.idx':        ('ANIM.PACK', 'animations'),
    'skeletons.idx':   ('SKEL.PACK', 'animations'),
}

# ============================================================================
# Copy & conversion engine
# ============================================================================

def generate_descr_caps_ex(dst_data: str) -> None:
    """Generate descr_caps_ex.txt with max factions limit for OG Rome."""
    cap_path = os.path.join(dst_data, 'descr_caps_ex.txt')
    if not os.path.exists(cap_path):
        with open(cap_path, 'w', encoding='cp1252', newline='\r\n') as f:
            f.write("max_factions 99\n")
        print(f"  GENERATE: data/descr_caps_ex.txt")


def is_terrain_cas_file(parts: list[str], fname: str) -> bool:
    """Check if file is a .cas inside the terrain/ directory tree."""
    return ('terrain' in parts or (len(parts) > 0 and parts[0] == 'terrain')) and fname.lower().endswith('.cas')


def convert_dir(src: str, dst: str, txt_only: bool = False, copy_skeletons: bool = False) -> None:
    copied = converted = skipped = 0
    idx_rebuilt = 0

    # Locate and load faction names from descr_sm_factions.txt
    descr_factions_path = None
    for r, d, fs in os.walk(src):
        for f in fs:
            if f.lower() == 'descr_sm_factions.txt':
                descr_factions_path = os.path.join(r, f)
                break
        if descr_factions_path:
            break

    faction_names = get_faction_names(descr_factions_path) if descr_factions_path else set()
    if faction_names:
        print(f"  Loaded {len(faction_names)} faction names for map TGA resizing")

    # Generate descr_caps_ex.txt in the root data folder
    generate_descr_caps_ex(dst)

    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        parts = [] if rel == '.' else rel.split(os.sep)

        if any(p in REMASTERED_ONLY_DIRS for p in parts):
            skipped += len(files)
            continue

        dst_dir = os.path.join(dst, rel)
        os.makedirs(dst_dir, exist_ok=True)

        for fname in files:
            src_file = os.path.join(root, fname)
            dst_file = os.path.join(dst_dir, fname)
            rel_file = fname if rel == '.' else os.path.join(rel, fname)

            # Skip Remastered-only file names
            if fname.lower() in REMASTERED_ONLY_FILES:
                print(f"  SKIP (new): {rel_file}")
                skipped += 1
                continue

            # Strip .cas files from terrain/ folder (OG Rome doesn't use them)
            if is_terrain_cas_file(parts, fname):
                print(f"  SKIP (terrain .cas): {rel_file}")
                skipped += 1
                continue

            # --txt-only mode: skip any non-.txt file
            if txt_only and not fname.lower().endswith('.txt'):
                print(f"  SKIP (--txt-only): {rel_file}")
                skipped += 1
                continue


            # ── Skip copying pack and skeletons (idx/dat) packs ──
            fname_lower = fname.lower()
            if fname_lower in ('pack.idx', 'pack.dat', 'skeletons.idx', 'skeletons.dat'):
                print(f"  SKIP (pack/skeletons): {rel_file}")
                skipped += 1
                continue

            # Binary – copy unchanged
            ext = os.path.splitext(fname)[1].lower()
            if ext in BINARY_EXT:
                is_campaign_dir = 'world/maps/campaign' in rel.replace('\\', '/').lower()
                is_faction_tga = False
                target_size = None
                if is_campaign_dir and fname.lower().endswith('.tga'):
                    name_part = fname[:-4].lower()
                    for faction in faction_names:
                        if faction.lower() in name_part:
                            is_faction_tga = True
                            if 'leader_pic' in name_part:
                                target_size = (70, 95)
                            else:
                                target_size = (395, 245)
                            break
                
                if is_faction_tga:
                    try:
                        from PIL import Image
                        resample_filter = getattr(Image, 'Resampling', Image)
                        filter_type = getattr(resample_filter, 'LANCZOS', getattr(resample_filter, 'BICUBIC', 2))
                        with Image.open(src_file) as img:
                            resized_img = img.resize(target_size, filter_type)
                            resized_img.save(dst_file)
                        print(f"  RESIZE TGA: {rel_file} to {target_size}")
                        converted += 1
                    except Exception as e:
                        print(f"  ERROR resizing TGA {rel_file}: {e} – copying raw")
                        shutil.copy2(src_file, dst_file)
                        copied += 1
                else:
                    shutil.copy2(src_file, dst_file)
                    copied += 1
                continue

            # Text – check for converter
            is_settlement_plan = any(x in ('settlement_plans', 'settlement_plan') for x in [p.lower() for p in parts]) and fname.lower().endswith('.txt')
            if fname.lower() in CONVERTERS or is_settlement_plan:
                try:
                    lines = read_file(src_file)
                    if is_settlement_plan:
                        result = conv_settlement_plan(lines)
                    else:
                        result = CONVERTERS[fname.lower()](lines)
                    write_file(dst_file, result)
                    print(f"  CONVERT: {rel_file}")
                    converted += 1
                except Exception as e:
                    print(f"  ERROR {rel_file}: {e} – copying raw")
                    shutil.copy2(src_file, dst_file)
                    copied += 1
            else:
                shutil.copy2(src_file, dst_file)
                copied += 1

    total = copied + converted + skipped + idx_rebuilt
    print(f"\n{'='*60}")
    print(f"  Done  |  copied: {copied}  converted: {converted}  skipped: {skipped}  idx_rebuilt: {idx_rebuilt}  total: {total}")
    print(f"  Output: {dst}")
    print(f"{'='*60}")


def help_text():
    return __doc__.strip()


def main():
    txt_only = '--txt-only' in sys.argv
    if txt_only:
        sys.argv.remove('--txt-only')

    copy_skeletons = '--copy-skeletons' in sys.argv
    if copy_skeletons:
        sys.argv.remove('--copy-skeletons')

    if len(sys.argv) != 3 or sys.argv[1] in ('-h', '--help'):
        print(help_text())
        sys.exit(0 if len(sys.argv) == 2 else 1)

    src, dst = sys.argv[1], sys.argv[2]

    if not os.path.isdir(src):
        print(f"ERROR: source '{src}' is not a directory.")
        sys.exit(1)
    if not os.path.exists(dst):
        os.makedirs(dst)

    if not HAS_IDX:
        print("NOTE: rtwx_idx.py not found - .idx/.dat packs will be copied as-is")
        print("      (individual animation files may still be copied separately)")
        print()

    print(f"Rome Remastered → OG Rome converter v{__version__}")
    print(f"  Source: {os.path.abspath(src)}")
    print(f"  Dest:   {os.path.abspath(dst)}")
    if txt_only:
        print(f"  Mode:   text files only (--txt-only)")
    if copy_skeletons:
        print(f"  Skeletons: copy as-is (--copy-skeletons)")
    print()
    convert_dir(src, dst, txt_only, copy_skeletons)


if __name__ == '__main__':
    main()