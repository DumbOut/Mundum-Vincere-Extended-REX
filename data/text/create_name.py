# Converts:
# {Ashoka}
# into:
# {Ashoka}Ashoka

INPUT_FILE = "input.txt"
OUTPUT_FILE = "names_export.txt"

output = []

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()

        if not line:
            continue

        # match {Name}
        if line.startswith("{") and line.endswith("}"):
            name = line[1:-1]
            output.append(f"{line}{name}")

# export new file
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print(f"Done -> {OUTPUT_FILE}")