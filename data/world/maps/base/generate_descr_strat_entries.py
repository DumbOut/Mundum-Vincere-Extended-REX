import re

def generate_descr_strat(input_file_path, output_file_path):
    with open(input_file_path, 'r') as f:
        content = f.read()

    # Regex to find the region internal name and the settlement name
    # It looks for a word ending in _R, then whitespace, then the settlement name
    pattern = re.compile(r'([a-zA-Z0-9_]+_R)\s+([a-zA-Z0-9_]+)')
    matches = pattern.findall(content)

    with open(output_file_path, 'w') as out:
        for region_name, settlement_name in matches:
            entry = f"""settlement
{{
    level town
    region {region_name}

    year_founded 0
    population 400
    plan_set default_set
    faction_creator parthia
    building
    {{
        type core_building governors_house
    }}
}}
"""
            out.write(entry)

# usage
generate_descr_strat('generate_desCr_strat_entries.txt', 'descr_strat_output.txt')