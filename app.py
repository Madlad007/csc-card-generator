"""CSC Tournament Card Generator.

Streamlit Community Cloud app for generating 1080x1350 soccer trading cards.
Dynamic text is drawn directly onto assets/background.png with fixed pixel
coordinates. Jersey/stat values are centered with ImageDraw.textbbox().
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, Tuple

import streamlit as st
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from rembg import remove


CARD_WIDTH = 1080
CARD_HEIGHT = 1350
BACKGROUND_PATH = Path("assets/background.png")
FOREGROUND_SPLASH_PATH = Path("assets/foreground_splashes.png")

# Dynamic text placement constants. Coordinates are tuned for a 1080x1350 card.
PLAYER_NAME_X = 105
PLAYER_NAME_Y = 205
PLAYER_NAME_FONT_SIZE = 92
PLAYER_NAME_COLOR = "#000000"

TEAM_NAME_X = 105
TEAM_NAME_Y = 440
TEAM_NAME_FONT_SIZE = 68
TEAM_NAME_COLOR = "#002B5C"

JERSEY_NUMBER_CENTER_X = 232
JERSEY_NUMBER_CENTER_Y = 861
JERSEY_NUMBER_FONT_SIZE = 135
JERSEY_NUMBER_COLOR = "#C99700"

SPEED_CENTER_X = 935
SPEED_CENTER_Y = 496
SHOOTING_CENTER_X = 935
SHOOTING_CENTER_Y = 700
PASSING_CENTER_X = 935
PASSING_CENTER_Y = 887
STAT_FONT_SIZE = 86
SPEED_COLOR = "#C99700"
SHOOTING_COLOR = "#002B5C"
PASSING_COLOR = "#C99700"

# Player placement remains unchanged from the prior subject-aware layout.
PLAYER_ZONE_X1 = 390
PLAYER_ZONE_Y1 = 160
PLAYER_ZONE_X2 = 740
PLAYER_ZONE_Y2 = 1120
FULL_BODY_TARGET_HEIGHT = 840
HALF_BODY_TARGET_HEIGHT = 720
CLOSE_UP_TARGET_HEIGHT = 600

FONT_CANDIDATES = (
    "assets/fonts/brush.ttf",
    "assets/fonts/BebasNeue-Regular.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)


st.set_page_config(page_title="CSC Tournament Card Generator", page_icon="⚽", layout="centered")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a large TrueType font, never Pillow's tiny bitmap default."""
    for font_path in FONT_CANDIDATES:
        path = Path(font_path)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue

    # DejaVuSans-Bold usually ships with Pillow and keeps Streamlit Cloud safe.
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except OSError:
        pass

    # Last resort: search common TrueType locations before failing loudly.
    common_roots = [Path("/usr/share/fonts"), Path("/Library/Fonts"), Path("C:/Windows/Fonts")]
    for root in common_roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*.ttf"):
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue

    raise RuntimeError(
        "No TrueType font found. Add assets/fonts/brush.ttf or assets/fonts/BebasNeue-Regular.ttf."
    )


def load_background() -> Image.Image:
    """Load the user-supplied background without modifying or regenerating it."""
    if BACKGROUND_PATH.exists():
        background = Image.open(BACKGROUND_PATH).convert("RGBA")
        if background.size != (CARD_WIDTH, CARD_HEIGHT):
            background = background.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        return background

    # Plain fallback only keeps the app usable when the required asset is missing.
    fallback = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), "#F6F1E4")
    draw = ImageDraw.Draw(fallback)
    draw.text((48, 48), "Add assets/background.png", fill="#7A4E00", font=load_font(42))
    return fallback


def alpha_bbox(image: Image.Image) -> Tuple[int, int, int, int] | None:
    """Return visible alpha bounds for an RGBA image."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getchannel("A").getbbox()


def clean_cutout(cutout: Image.Image) -> Image.Image:
    """Remove fringe, crop alpha bounds, and slightly enhance the player cutout."""
    cutout = cutout.convert("RGBA")
    bbox = alpha_bbox(cutout)
    if bbox:
        cutout = cutout.crop(bbox)

    r, g, b, a = cutout.split()
    # Tighten soft rembg fringe without creating a rectangular backing layer.
    a = a.filter(ImageFilter.MedianFilter(size=3))
    a = ImageEnhance.Contrast(a).enhance(1.25)
    cutout = Image.merge("RGBA", (r, g, b, a))
    cutout = ImageEnhance.Contrast(cutout).enhance(1.05)
    cutout = ImageEnhance.Sharpness(cutout).enhance(1.08)
    return cutout


def classify_shot(cutout: Image.Image) -> str:
    """Classify approximate crop type using visible cutout proportions."""
    w, h = cutout.size
    aspect = w / max(h, 1)
    if h > w * 2.05 or aspect < 0.46:
        return "full_body"
    if h > w * 1.35:
        return "half_body"
    return "close_up"


def resize_player(cutout: Image.Image, shot_type: str) -> Image.Image:
    """Resize the player to the unchanged subject-aware target heights."""
    target_heights = {
        "full_body": FULL_BODY_TARGET_HEIGHT,
        "half_body": HALF_BODY_TARGET_HEIGHT,
        "close_up": CLOSE_UP_TARGET_HEIGHT,
    }
    target_height = target_heights.get(shot_type, HALF_BODY_TARGET_HEIGHT)
    scale = target_height / max(cutout.height, 1)
    target_width = max(1, int(cutout.width * scale))
    return cutout.resize((target_width, target_height), Image.Resampling.LANCZOS)


def player_position(player: Image.Image, shot_type: str) -> Tuple[int, int]:
    """Place the player inside the unchanged player zone without any grey backing."""
    zone_width = PLAYER_ZONE_X2 - PLAYER_ZONE_X1
    x = PLAYER_ZONE_X1 + (zone_width - player.width) // 2

    if shot_type == "full_body":
        foot_y = PLAYER_ZONE_Y2
        y = foot_y - player.height
    elif shot_type == "close_up":
        y = PLAYER_ZONE_Y1 + 84
    else:
        y = PLAYER_ZONE_Y1 + 185

    return int(x), int(y)


def add_player_shadow(card: Image.Image, player: Image.Image, x: int, y: int) -> None:
    """Blend the cutout with soft shadow/glow only; no rectangle is drawn."""
    alpha = player.getchannel("A")
    shadow = Image.new("RGBA", player.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(18)).point(lambda p: int(p * 0.34)))
    card.alpha_composite(shadow, (x + 16, y + 22))

    glow = Image.new("RGBA", player.size, (255, 232, 164, 0))
    glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(10)).point(lambda p: int(p * 0.12)))
    card.alpha_composite(glow, (x, y))


def composite_player(card: Image.Image, source_photo: Image.Image) -> Image.Image:
    """Remove the photo background and place the player; placement logic unchanged."""
    removed = remove(source_photo.convert("RGBA"))
    cutout = clean_cutout(removed)
    shot_type = classify_shot(cutout)
    player = resize_player(cutout, shot_type)
    x, y = player_position(player, shot_type)

    add_player_shadow(card, player, x, y)
    card.alpha_composite(player, (x, y))

    if FOREGROUND_SPLASH_PATH.exists():
        foreground = Image.open(FOREGROUND_SPLASH_PATH).convert("RGBA")
        if foreground.size != (CARD_WIDTH, CARD_HEIGHT):
            foreground = foreground.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        card.alpha_composite(foreground)

    return card


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    center_y: int,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    """Center text exactly around a pixel-picker center point using textbbox()."""
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = center_x - width / 2 - bbox[0]
    y = center_y - height / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def draw_text_values(
    card: Image.Image,
    player_name: str,
    team_name: str,
    jersey_number: str,
    speed: int,
    shooting: int,
    passing: int,
) -> Image.Image:
    """Draw only entered dynamic values; no label text or background rectangles."""
    draw = ImageDraw.Draw(card)
    player_font = load_font(PLAYER_NAME_FONT_SIZE)
    team_font = load_font(TEAM_NAME_FONT_SIZE)
    jersey_font = load_font(JERSEY_NUMBER_FONT_SIZE)
    stat_font = load_font(STAT_FONT_SIZE)

    draw.text(
        (PLAYER_NAME_X, PLAYER_NAME_Y),
        player_name.upper().strip(),
        font=player_font,
        fill=PLAYER_NAME_COLOR,
    )
    draw.text(
        (TEAM_NAME_X, TEAM_NAME_Y),
        team_name.upper().strip(),
        font=team_font,
        fill=TEAM_NAME_COLOR,
    )

    draw_centered_text(
        draw,
        str(jersey_number).strip(),
        JERSEY_NUMBER_CENTER_X,
        JERSEY_NUMBER_CENTER_Y,
        jersey_font,
        JERSEY_NUMBER_COLOR,
    )
    draw_centered_text(draw, str(speed), SPEED_CENTER_X, SPEED_CENTER_Y, stat_font, SPEED_COLOR)
    draw_centered_text(
        draw,
        str(shooting),
        SHOOTING_CENTER_X,
        SHOOTING_CENTER_Y,
        stat_font,
        SHOOTING_COLOR,
    )
    draw_centered_text(
        draw,
        str(passing),
        PASSING_CENTER_X,
        PASSING_CENTER_Y,
        stat_font,
        PASSING_COLOR,
    )
    return card


def generate_card(
    photo_bytes: bytes,
    player_name: str,
    team_name: str,
    jersey_number: str,
    speed: int,
    shooting: int,
    passing: int,
) -> Image.Image:
    """Build the final PNG card entirely in memory."""
    with Image.open(io.BytesIO(photo_bytes)) as uploaded:
        source_photo = ImageOps.exif_transpose(uploaded).convert("RGBA")

    card = load_background()
    card = composite_player(card, source_photo)
    card = draw_text_values(card, player_name, team_name, jersey_number, speed, shooting, passing)
    return card.convert("RGBA")


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def read_uploaded_bytes(files: Iterable) -> bytes | None:
    for file in files:
        if file is not None:
            return file.getvalue()
    return None


def main() -> None:
    st.title("CSC Tournament Card Generator")
    st.caption("Create a 1080×1350 tournament trading card from a camera photo or upload.")

    with st.form("card_form"):
        player_name = st.text_input("Player Name", value="Player Name")
        team_name = st.text_input("Team Name", value="Team Name")
        jersey_number = st.text_input("Jersey Number", value="10")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            speed = st.slider("Speed", 1, 99, 88)
        with col_b:
            shooting = st.slider("Shooting", 1, 99, 91)
        with col_c:
            passing = st.slider("Passing", 1, 99, 84)

        camera_photo = st.camera_input("Take player photo")
        uploaded_photo = st.file_uploader(
            "Or upload player photo",
            type=("png", "jpg", "jpeg", "webp"),
            accept_multiple_files=False,
        )
        submitted = st.form_submit_button("Generate card", type="primary")

    if not submitted:
        st.info("Enter card details and add a player photo to generate a PNG.")
        return

    photo_bytes = read_uploaded_bytes((camera_photo, uploaded_photo))
    if photo_bytes is None:
        st.error("Please take or upload a player photo before generating the card.")
        return

    try:
        with st.spinner("Compositing player and drawing card text…"):
            card = generate_card(
                photo_bytes=photo_bytes,
                player_name=player_name,
                team_name=team_name,
                jersey_number=jersey_number,
                speed=speed,
                shooting=shooting,
                passing=passing,
            )
            png_bytes = image_to_png_bytes(card)
    except Exception as exc:  # Keep unsupported/corrupt uploads from crashing the app.
        st.error("This image could not be processed. Try a clearer JPG or PNG player photo.")
        st.exception(exc)
        return

    st.image(png_bytes, caption="Generated CSC tournament card", use_container_width=True)
    st.download_button(
        "Download PNG",
        data=png_bytes,
        file_name=f"{player_name.strip().replace(' ', '_') or 'player'}_csc_card.png",
        mime="image/png",
        type="primary",
    )


if __name__ == "__main__":
    main()
