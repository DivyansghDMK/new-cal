import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

def make_chrome_style_cardiox_icon():
    src_path = os.path.join("assets", "cardiox_logo.png")
    ico_path = os.path.join("assets", "cardiox_logo.ico")
    bold_png_path = os.path.join("assets", "cardiox_logo_bold.png")

    img = Image.open(src_path).convert("RGBA")
    arr = np.array(img, dtype=np.float32)

    # 1. Identify background dark color vs heart symbol
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]

    # Mask for heart symbol (orange/gold/red/white text)
    symbol_mask = (r > 60) | (g > 80) | (b > 120) | (r > g + 10)

    # Find tight bounding box around actual heart + CardioX text
    coords = np.argwhere(symbol_mask)
    if len(coords) > 0:
        ymin, xmin = coords.min(axis=0)
        ymax, xmax = coords.max(axis=0)
    else:
        ymin, xmin, ymax, xmax = 0, 0, img.height, img.width

    # Crop tight symbol
    crop_w = xmax - xmin
    crop_h = ymax - ymin
    
    # Square crop
    max_dim = max(crop_w, crop_h)
    cx, cy = (xmin + xmax) // 2, (ymin + ymax) // 2
    
    sq_xmin = max(0, cx - max_dim // 2)
    sq_xmax = min(img.width, cx + max_dim // 2)
    sq_ymin = max(0, cy - max_dim // 2)
    sq_ymax = min(img.height, cy + max_dim // 2)

    symbol_crop = img.crop((sq_xmin, sq_ymin, sq_xmax, sq_ymax))

    # 2. Build high-res Chrome-style circular 3D badge (512x512)
    size = 512
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    draw = ImageDraw.Draw(badge)
    margin = 16

    # Draw circular gradient background (Deep Indigo Blue #0A192F to #1E3A8A)
    for r_i in range(size // 2 - margin, 0, -1):
        cx_c, cy_c = size // 2, size // 2
        t = r_i / (size // 2 - margin)
        cr = int(10 + (30 - 10) * (1 - t))
        cg = int(25 + (70 - 25) * (1 - t))
        cb = int(47 + (160 - 47) * (1 - t))
        draw.ellipse([cx_c - r_i, cy_c - r_i, cx_c + r_i, cy_c + r_i], fill=(cr, cg, cb, 255))

    # Outer border ring (vibrant glowing orange/gold edge like Chrome)
    draw.ellipse([margin, margin, size - margin, size - margin], outline=(255, 120, 0, 255), width=8)

    # 3. Resize tight symbol to fill 88% of badge
    sym_size = int(size * 0.82)
    symbol_resized = symbol_crop.resize((sym_size, sym_size), Image.Resampling.LANCZOS)

    # Enhance saturation & contrast of the heart symbol
    enhancer = ImageEnhance.Color(symbol_resized)
    symbol_resized = enhancer.enhance(1.4)
    contrast = ImageEnhance.Contrast(symbol_resized)
    symbol_resized = contrast.enhance(1.2)

    # Make background of symbol transparent inside the circle
    sym_arr = np.array(symbol_resized, dtype=np.float32)
    sr, sg, sb = sym_arr[:,:,0], sym_arr[:,:,1], sym_arr[:,:,2]
    bg_mask = (sr < 45) & (sg < 55) & (sb < 80)
    sym_arr[bg_mask, 3] = 0
    
    clean_symbol = Image.fromarray(sym_arr.astype(np.uint8), "RGBA")

    # Paste symbol centrally onto circular badge
    paste_pos = ((size - sym_size) // 2, (size - sym_size) // 2)
    badge.alpha_composite(clean_symbol, paste_pos)

    # Save high-res bold PNG
    badge.save(bold_png_path, format="PNG")
    print(f"Saved bold PNG to {bold_png_path}")

    # 4. Generate multi-resolution .ico file for Windows taskbar (256, 128, 64, 48, 32, 16)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    badge.save(ico_path, format="ICO", sizes=sizes)
    print(f"Successfully generated bold multi-resolution ICO at {ico_path}")

if __name__ == "__main__":
    make_chrome_style_cardiox_icon()
