# rr2rex - Rome Remastered to OG Rome Mod Converter

A Python script that converts mods made for **Total War: Rome Remastered** back to the **original Rome: Total War** format.

## Why?

If you have a mod built for Rome Remastered and want to make it compatible with the original Rome: Total War (Gold edition), this script handles all the file format differences between the two versions automatically.

## Quick Start

```
python rr2rex.py <remastered_mod_data_folder> <output_og_folder>
```

Example:
```
python rr2rex.py "D:\MyMod\data" "D:\MyMod_OG\data"
```

## What it does

Based on the comprehensive analysis at [TWC Wiki: File Differences - Rome Remastered](https://wiki.twcenter.net/index.php?title=File_Differences_-_Rome_Remastered):

### Files copied as-is (~most files)
Text files whose format hasn't changed between versions are simply copied with relative paths preserved. Binary files (.cas, .tga, .dds, .db, etc.) are also copied unchanged.

### Files automatically converted (back to OG format)
| File | Conversion |
|------|-----------|
| `descr_character.txt` | Removes the new `type merchant` section |
| `export_descr_unit.txt` | Removes `voice_indexes`, `ethnicity`, `is_female`, `hair_*`, `tattoo_color`; removes `rebalance_statblock` sections; converts animal type names back (wardog→wardogs, pig→pigs) |
| `export_descr_buildings.txt` | Strips Remastered-only conditions: `tavern_bonus`, `currency_fixed`, `remastered_only`, `is_player`, etc. |
| `descr_sm_factions.txt` | Strips `ethnicity`, `ftree_*_colour` attributes |
| `descr_strat.txt` | Converts AI personality names (`comfortable_caesar`→`comfortable caesar`); strips resource quantity from trade resources |
| `descr_win_conditions.txt` | Adds a note about settlement name vs region name requirement change |
| `descr_model_battle.txt` | **Major conversion**: converts new `model <ethnicity> <path>` format back to OG `model_flexi_m` with LOD entries, sprite, and triangle references |
| `descr_model_strat.txt` | Same model format conversion for strat models |
| `descr_aerial_map_bases.txt` | Removes `size` attribute |
| `descr_animals.txt` | Removes `width` and `offset` attributes |
| `descr_climates.txt` | Removes `dust_color`, `mud_color`, `mountain`, `coarse_detail` |
| `descr_cultures.txt` | Removes merchant cost/UI lines |
| `descr_cursor_actions.txt` | Removes merchant cursor entries |
| `descr_custom_locations.txt` | Removes `sandstorm` attribute |
| `descr_daytypes.txt` | Removes `grunge` attribute and `sand_storm` events |
| `descr_engines.txt` | Removes `engine_outline`, `collapse_effect`, new sound types |
| `descr_event_enums.txt` | Removes new merchant events, new fonts, `dark_brown` color |
| `descr_mount.txt` | Removes `water_trail_effect_running` |
| `descr_particle.txt` | Removes `normal_map`, `shading`, `friction` attrs; new particle types |
| `descr_projectile_new.txt` | Removes `min_velocity` and `javelin_with_pilum_skin` |
| `descr_strat_sundries.txt` | Removes `resource_hover` and `watch_tower_hover` types |
| `export_descr_advice.txt` | Removes `Manual` attribute and new condition names |
| `export_descr_character_traits.txt` | Removes new conditions/effects (`Toggled`, `RemasteredEducation`, etc.) |
| `export_descr_ancillaries.txt` | Same as traits |

### Files generated
| File | Content | Purpose |
|------|---------|---------|
| `descr_caps_ex.txt` | `max_factions 99` | Allows OG Rome to handle the larger faction count from Remastered mods |

### Files skipped (Remastered-only, no OG equivalent)
New Remastered files like `descr_campaigns.txt`, `feral_*.txt`, `descr_unit_variation.txt`, `descr_fog_params.txt`, etc. are skipped. New directories like `characters/`, `animals/`, `feral_textures/`, `original_overrides/`, etc. are also skipped.

## Requirements

- Python 3.6+
- No external dependencies (uses only standard library)

## Notes

1. **descr_sm_resources.txt**: The Remastered version uses a substantially different format. This file is passed through as-is - you may need to manually adapt it.
2. **descr_model_battle.txt / descr_model_strat.txt**: The auto-generated `model_flexi_m` entries point to approximate LOD files that may not exist in your OG setup. You'll likely need to adjust model paths, sprite references, and distance values.
3. **descr_win_conditions.txt**: Remastered uses settlement names where OG uses region names. The script adds a warning comment but cannot auto-convert these without `descr_regions.txt`.
4. Files marked as "no longer functional" in Remastered (like `descr_grass.txt`, `descr_skydome.txt`, `descr_pallete.txt`, etc.) are still **copied** as-is since they ARE functional in OG Rome.