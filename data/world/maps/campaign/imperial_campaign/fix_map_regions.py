import logging
from PIL import Image
import numpy as np
import os
from collections import defaultdict

# =========================
# CONFIG
# =========================
INPUT_PATH = "map_regions.tga"
OUTPUT_PATH = "map_regions_fixed.tga"
DEBUG_PATH = "map_regions_debug.tga"
LOG_PATH = "map_regions_fix.log"

EXPECTED_SIZE = (1495, 624)

BLACK = (0, 0, 0)     # city
WHITE = (255, 255, 255)  # port
RED = (255, 0, 0)     # invalid marker
YELLOW = (255, 255, 0)  # invalid coast

SEA_BASE = (41, 140)

# =========================
# LOGGING SETUP
# =========================
logging.basicConfig(
    filename=LOG_PATH,
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter('%(levelname)s | %(message)s'))
logging.getLogger().addHandler(console)

# =========================
# LOAD IMAGE
# =========================
img = Image.open(INPUT_PATH).convert("RGB")

if img.size != EXPECTED_SIZE:
    logging.error(f"Invalid image size {img.size}, expected {EXPECTED_SIZE}")
    raise ValueError("Incorrect map size")

pixels = np.array(img)
debug_pixels = pixels.copy()

height, width, _ = pixels.shape

logging.info(f"Loaded map {INPUT_PATH} ({width}x{height})")

# =========================
# HELPERS
# =========================
def is_sea(color):
    return color[0] == SEA_BASE[0] and color[1] == SEA_BASE[1]

def get_neighbors(x, y):
    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny

def find_region(x, y):
    for nx, ny in get_neighbors(x, y):
        c = tuple(pixels[ny, nx])
        if c not in (BLACK, WHITE) and not is_sea(c):
            return c
    return None

def is_valid_marker(x, y, region):
    for nx, ny in get_neighbors(x, y):
        c = tuple(pixels[ny, nx])
        if c not in (region, BLACK, WHITE) and not is_sea(c):
            return False
    return True

# =========================
# SCAN REGIONS
# =========================
region_pixels = defaultdict(list)

for y in range(height):
    for x in range(width):
        c = tuple(pixels[y, x])
        if c not in (BLACK, WHITE):
            region_pixels[c].append((x, y))

logging.info(f"Detected {len(region_pixels)} regions")

# warn tiny regions
for r, coords in region_pixels.items():
    if len(coords) < 5:
        logging.warning(f"Small region {r}: {len(coords)} pixels")

# =========================
# FIND MARKERS
# =========================
cities = []
ports = []

for y in range(height):
    for x in range(width):
        c = tuple(pixels[y, x])
        if c == BLACK:
            cities.append((x, y))
        elif c == WHITE:
            ports.append((x, y))

logging.info(f"Found {len(cities)} city markers")
logging.info(f"Found {len(ports)} port markers")

# =========================
# ASSIGN MARKERS
# =========================
region_city = {}
region_port = {}

def clean_markers(marker_list, name):
    assigned = {}

    for x, y in marker_list:
        region = find_region(x, y)

        if not region:
            logging.warning(f"{name} at {(x,y)} unassigned -> removed")
            debug_pixels[y, x] = RED
            continue

        if region in assigned:
            logging.warning(f"Duplicate {name} in {region} at {(x,y)} removed")
            pixels[y, x] = region
            continue

        if not is_valid_marker(x, y, region):
            logging.warning(f"Invalid {name} placement at {(x,y)} in {region}")
            debug_pixels[y, x] = RED
            pixels[y, x] = region
            continue

        assigned[region] = (x, y)

    return assigned

region_city = clean_markers(cities, "City")
region_port = clean_markers(ports, "Port")

# =========================
# FIX MISSING CITIES
# =========================
for region, coords in region_pixels.items():
    if len(coords) < 5:
        continue

    if region not in region_city:
        x, y = coords[len(coords)//2]
        pixels[y, x] = BLACK
        region_city[region] = (x, y)
        logging.info(f"Added missing city for {region} at {(x,y)}")

# =========================
# FIX PORTS (COAST LOGIC)
# =========================
for region, coords in region_pixels.items():

    if len(coords) < 5:
        continue

    coast = []

    for x, y in coords:
        for nx, ny in get_neighbors(x, y):
            if is_sea(tuple(pixels[ny, nx])):
                coast.append((x, y))
                break

    if coast:
        if region not in region_port:
            placed = False

            for x, y in coast:
                if is_valid_marker(x, y, region):
                    pixels[y, x] = WHITE
                    region_port[region] = (x, y)
                    logging.info(f"Added port for {region} at {(x,y)}")
                    placed = True
                    break

            if not placed:
                logging.warning(f"No valid port spot for {region}")
                for x, y in coast:
                    debug_pixels[y, x] = YELLOW
    else:
        if region in region_port:
            x, y = region_port[region]
            pixels[y, x] = region
            logging.info(f"Removed inland port from {region}")

# =========================
# SAVE OUTPUTS
# =========================
Image.fromarray(pixels.astype('uint8')).save(OUTPUT_PATH, format='TGA')
Image.fromarray(debug_pixels.astype('uint8')).save(DEBUG_PATH, format='TGA')

logging.info(f"Saved fixed map -> {OUTPUT_PATH}")
logging.info(f"Saved debug map -> {DEBUG_PATH}")
logging.info("DONE")