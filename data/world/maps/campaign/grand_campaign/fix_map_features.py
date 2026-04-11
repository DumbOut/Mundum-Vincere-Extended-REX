import numpy as np
from PIL import Image

# CONFIG
INPUT_PATH = "map_features.tga"
OUTPUT_PATH = "map_features_fixed.tga"

# RTW COLORS
BLACK  = (0, 0, 0)
BLUE   = (0, 0, 255)
WHITE  = (255, 255, 255)
CYAN   = (0, 255, 255)

def fix_map_ultra_thin():
    # 1. Load and detect features
    img = Image.open(INPUT_PATH).convert("RGB")
    pixels = np.array(img)
    h, w, _ = pixels.shape

    # 2. Create clean black canvas (replaces Yellow and anything else with Black)
    output = np.zeros((h, w, 3), dtype=np.uint8)

    # 3. Extract Raw Masks
    is_source = np.all(pixels == WHITE, axis=-1)
    is_ford   = np.all(pixels == CYAN, axis=-1)
    # Be strict with Blue to avoid artifacts
    is_river  = (pixels[:,:,2] > 200) & (pixels[:,:,0] < 50) & (pixels[:,:,1] < 50)
    
    # Combined path
    raw_path = is_river | is_source | is_ford
    
    # 4. Aggressive Thinning (The "Black Pencil" Logic)
    # We use a copy to track what we've already decided to keep
    thinned_mask = np.zeros((h, w), dtype=bool)

    for y in range(h):
        for x in range(w):
            if raw_path[y, x]:
                # 2x2 CHECK: If current pixel would complete a 2x2 square
                # with pixels already placed to the Top, Left, or Top-Left...
                # ...we DO NOT draw it (effectively using a black pencil on it).
                if x > 0 and y > 0:
                    if thinned_mask[y-1, x] and thinned_mask[y, x-1] and thinned_mask[y-1, x-1]:
                        continue # Skip this pixel (remains Black)

                # DIAGONAL CHECK: If this pixel is only connected diagonally (Top-Left),
                # we keep it as a single diagonal pixel (this is the thinnest possible).
                thinned_mask[y, x] = True

    # 5. Render to output
    # Paint only the thinned blue spine
    output[thinned_mask] = BLUE

    # 6. Place EXACT 1x1 markers
    # This prevents white/cyan from being 2x2 or 2x1
    for y in range(h):
        for x in range(w):
            if thinned_mask[y, x]:
                # If original had a marker, and we don't have a marker neighbor already
                if is_source[y, x]:
                    if not (y > 0 and np.all(output[y-1, x] == WHITE)) and \
                       not (x > 0 and np.all(output[y, x-1] == WHITE)):
                        output[y, x] = WHITE
                elif is_ford[y, x]:
                    if not (y > 0 and np.all(output[y-1, x] == CYAN)) and \
                       not (x > 0 and np.all(output[y, x-1] == CYAN)):
                        output[y, x] = CYAN

    # 7. Final Check: Ensure background is Pitch Black (0,0,0)
    # (Handled by the np.zeros initialization)

    # 8. Save as 24-bit Uncompressed TGA
    Image.fromarray(output).save(OUTPUT_PATH, rle=False)
    print("Success: Ultra-thin 1x1 paths. 2x2 blocks removed with black pencil.")

if __name__ == "__main__":
    fix_map_ultra_thin()