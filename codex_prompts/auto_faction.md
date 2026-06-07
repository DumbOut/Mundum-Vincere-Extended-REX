You are modifying a Rome Total War / OpenRTW / REX workspace.

TASK:
Add a new template faction with NO new units or textures.  
The faction uses existing slave/vanilla units but has its own which you will create
- campaign banner texrt
- battle banner text
- building banner text
- UI icon text
- menu select icons
- faction metadata
- names (optional)
- descr_strat entry
- region ownership (faction creator)
- units_info + units folder using SLAVE unit cards

Do NOT create new unit models or textures.  
Do NOT edit map_regions.tga except for reading coordinates.  
Do NOT create new EDU entries except adding ownership to existing units.

MODULAR HEADER:
faction: <FACTION_NAME>
culture: <CULTURE_NAME>

Example:
faction: itanos_01
culture: greek

REGIONS TO OCCUPY:
Itanos_R

-----------------------------------------
GLOBAL RULES FOR ALL FILE EDITS
-----------------------------------------
1. Preserve all whitespace, indentation, loc notes ";" and RTW formatting.
2. Append new blocks at the correct alphabetical or logical position.
3. Never overwrite existing factions.
4. Never remove any vanilla content except:
   - Remove region ownership from old faction
   - Remove characters from that region
5. Use comments:  ;; <faction> START  /  ;; <faction> END
6. If a file already contains the faction, skip it.
7. When assigning region ownership:
   - Remove the region from its previous faction
   - Remove any characters stationed there
8. When finding coordinates for descr_strat:
   - INVERT map_regions.tga VERTICALLY once before reading pixel coordinates
   - Use the flipped vertically once
9. Prefer SLAVE textures for DMB and DMS ownership additions.
10. Create a new folder:
      data/ui/units/<faction>
      data/ui/unit_info/<faction>
    Copy SLAVE unit cards into these folders.
11. When adding names:
    - Append a new namelist to descr_names.txt
    - Also append to text/names.txt
    - Use the nearest cultural namelist as a template (e.g., greek → greek_cities, macedon, seleucid)
12. When reading region RGB:
    - Read map_regions.tga pixel RGB for the region color
    - Identify the region by matching RGB to descr_regions.txt
    - Detect the black settlement pixel (0,0,0) inside the region
    - Use the black pixel’s coordinates (after vertical inversion) for descr_strat settlement placement

-----------------------------------------
FILES TO EDIT (DATA FOLDER)
-----------------------------------------

### 1. descr_sm_factions.txt
- Add a new faction block using the template faction header.
- Assign:
  - culture
  - symbol index
  - primary color
  - secondary color
  - standard index
  - custom banner paths (campaign/battle/building)
  - UI icon path

### 2. descr_banners.txt
- Add campaign and battle banner entries for the new faction.
- Use existing banner models; only change textures.

### 3. descr_building_battle.txt
- Add building banner entry referencing the same texture as battle banner.

### 4. descr_character.txt
- Add faction to valid general/captain/spy/diplomat pools.

### 5. descr_lbc_db.txt
- Add faction to the LBC block.

### 7. descr_model_battle.txt
- Do NOT add new models.
- Only add texture ownership lines for existing units.
- ALWAYS prefer slave textures.

### 8. descr_model_strat.txt
- Add strat general/captain/diplomat/spy models using existing culture models and textures.

### 9. descr_names.txt
- Append a new namelist for the faction.
- Use nearest cultural namelist as template.

### 10. descr_offmap_models.txt
- Add faction to offmap model ownership if needed.

### 12. export_descr_buildings.txt
- Add faction to building ownership where appropriate.
- Add EDU ownership for units used by the faction.

### 13. export_descr_unit.txt
- Add faction ownership to selected vanilla units.
- Do NOT create new units.

-----------------------------------------
FILES TO EDIT (TEXT FOLDER)
-----------------------------------------

### 14. campaign_descriptions.txt
- Add faction description block.

### 15. expanded_bi.txt
- Add UI strings based off pre-existing entry blocks.

### 16. names.txt
- Append the same namelist added to descr_names.txt.

-----------------------------------------
FILES TO EDIT (WORLD/BASE FOLDER)
-----------------------------------------

### 17. descr_strat.txt
- Add faction block.
- Add random faction name + family tree.
- Add starting characters.
- Add starting army using existing units.
- Add region ownership for Itanos_R.
- Use coordinates found by:
  - Inverting map_regions.tga vertically
  - Reading pixel location of Itanos_R region color
  - Finding the black settlement pixel (0,0,0)
  - Converting to descr_strat coordinates

### 18. descr_regions.txt
- Modify faction creator if assigning a region to the new faction.
- Confirm RGB matches map_regions.tga.

### 19. descr_win_conditions.txt
- Add victory conditions for the new faction.

-----------------------------------------
UI FILES TO CREATE
-----------------------------------------

### 20. data/ui/units/<faction>
- Copy all SLAVE unit cards here (but only appropriate units owned by Itanos)

### 21. data/ui/unit_info/<faction>
- Copy all SLAVE unit_info cards here. (but only appropriate units owned by Itanos)

Unit Pool, don't include un-necessary units or unrelated 

Greek/Cretan/Egyptian mix

Make an extremely detailed namelists and export to names.txt at the bottom foolow convention

Also for descr_strat make a correct family tree and follow convention already

-----------------------------------------
OUTPUT FORMAT
-----------------------------------------
For each file:
1. Show the exact block to insert.
2. Use RTW-accurate formatting.
3. Wrap each block with:
   ;; <faction>
4. Do not include commentary outside the blocks.

logo_index
small_logo_index 

replace these too

Also generate an extremely detailed faction description including tons of real world history and mythic/folklore data if needed - 11 paragrpahs

-----------------------------------------
BEGIN USING THE FOLLOWING EXAMPLE:
faction: itanos_01
culture: greek
-----------------------------------------
