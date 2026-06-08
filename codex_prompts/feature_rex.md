OPtimize and copy mp battle ui style to mp campaign and complete New Feature reqeusts


1. Enable horde spawn anywhere event instead of only on the edge of map, preferably with one coordinate as a radius area in descr_strat
2. Allow hordes to start on horde fleets aka sea tiles with an admiral/navy
3. Culture-based naming conventions flags in descr_namelists.txt last names going first
4. Multiple Family Trees with names and a switchable by button family tree 
5. annex_faction romeshell command
6. give_gold_random_doomstack romeshell command and silver and bronze and mixed too, only faction owned units
7. The ability for all unmarried vanilla female family members to be "princesses" so multiple family trees in the same faction can "interact"
8. Ability set the population required to upgrade settlement from settlement levels descr_cultures.txt aka 24000 to 36000 just like Family / character ageing, horde & bribery settings in descr_ex.txt
9. Fix copy, cut and paste in romeshell
10. Prevent factions from attacking eachother in descr_strat aka Codeable in descr_strat like  "ai_do_not_attack_faction", but also not attacking the player faction, I suggest to name it " ai_do_not_attack_player_faction"
11. ai_ignore_rebels flag in descr_strat aka ignore vanilla slave faction
12. Balance new raid trade routes mechanic so it's less econmocially cheesing
13. Grant settlement to protectorates settlement capture choice
14. Fix sttlement capture options slider and make the options smaller
15. Add  recently_captured counter for scripting
16. The ability to resurrect a dead faction region creator in the capture settlement options if you capture one of it's starting settlements. The faction becomes a protectorates
17. Add new EDU unit attributes:

    * `anti_horde` — bonus morale/damage when fighting horde armies
    * `river_crossing_bonus` — reduced penalties when fighting on river crossings
    * `desert_raider` — reduced fatigue and movement penalties in desert climates
    * `forest_ambusher` — bonus attack/morale when hidden in forests
    * `siege_looter` — extra post-battle income when capturing settlements
18. Add `client_kingdom_only_units` recruitment flag
    Allow certain units to be recruitable only by factions under protectoratess status, resurrected factions, protectorates, or factions marked as subjects in `descr_strat`.
19. Add `regional_revolt_faction` in `descr_regions.txt`
    Let each region define which dead/emergent faction should spawn during revolts instead of always using rebels/slaves.


    
20. Addable custom climate types packed as descr_ex_custom_climates.txt and inputtable in the climates file
21. The ability to liberate faction region creator in the capture settlement options if you capture one of it's starting settlements. The faction becomes a protectorates
22. A scripting function that renames the settlement based on your culture/faction (if there's an endonym available)
23. Add the possiblity faction without family members similar to tectonic order.  Useful for democracies like Athens.
24. Add an optional tertiary color in descr_sm_factions.txt that is configurable in descr_ex and also appears on the mid overlayed outside the secondary color, but isn't needed