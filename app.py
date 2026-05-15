import base64
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, UnidentifiedImageError
from rembg import remove

try:
    from openai import OpenAI
except Exception:  # OpenAI is optional at runtime; rembg-only mode still works.
    OpenAI = None


# -----------------------------------------------------------------------------
# Card and asset configuration
# -----------------------------------------------------------------------------
CARD_WIDTH = 1080
CARD_HEIGHT = 1350
BACKGROUND_PATH = Path("assets/background.png")
FOREGROUND_SPLASHES_PATH = Path("assets/foreground_splashes.png")

# Text placement constants tuned for the current 1080x1350 background artwork.
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
SPEED_COLOR = "#C99700"

SHOOTING_CENTER_X = 935
SHOOTING_CENTER_Y = 700
SHOOTING_COLOR = "#002B5C"

PASSING_CENTER_X = 935
PASSING_CENTER_Y = 887
PASSING_COLOR = "#C99700"

STAT_FONT_SIZE = 86

# Player placement constants. Keep these separate for easy future tuning.
PLAYER_ZONE_X1 = 390
PLAYER_ZONE_Y1 = 160
PLAYER_ZONE_X2 = 740
PLAYER_ZONE_Y2 = 1120

FULL_BODY_TARGET_HEIGHT = 840
HALF_BODY_TARGET_HEIGHT = 720
CLOSE_UP_TARGET_HEIGHT = 600

FONT_CANDIDATES = [
    "assets/fonts/brush.ttf",
    "assets/fonts/BebasNeue-Regular.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


# -----------------------------------------------------------------------------
# Streamlit page setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CSC Tournament Card Generator",
    page_icon="⚽",
    layout="centered",
)

st.title("CSC Tournament Card Generator")
st.caption("Create a 1080×1350 tournament trading card from a player photo.")


# -----------------------------------------------------------------------------
# Font helpers
# -----------------------------------------------------------------------------
def load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a large TrueType font. Never fall back to PIL's tiny bitmap font."""
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        try:
            if path.exists() or candidate.startswith("C:/Windows") or candidate.startswith("/"):
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue

    # Last-resort TrueType names commonly discoverable by Pillow/fontconfig.
    for font_name in ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]:
        try:
            return ImageFont.truetype(font_name, size=size)
        except Exception:
            continue

    raise RuntimeError(
        "No usable TrueType font found. Add assets/fonts/brush.ttf or "
        "assets/fonts/BebasNeue-Regular.ttf, or install DejaVu/Arial fonts."
    )


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    """Center text horizontally and vertically around an exact pixel point."""
    value = str(text)
    bbox = draw.textbbox((0, 0), value, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = center_x - width / 2 - bbox[0]
    y = center_y - height / 2 - bbox[1]
    draw.text((x, y), value, font=font, fill=fill)


def draw_card_text(
    card: Image.Image,
    player_name: str,
    team_name: str,
    jersey_number: str,
    speed: int,
    shooting: int,
    passing: int,
) -> Image.Image:
    """Draw only the entered values, with no debug text or backing rectangles."""
    draw = ImageDraw.Draw(card)

    player_font = load_font(PLAYER_NAME_FONT_SIZE)
    team_font = load_font(TEAM_NAME_FONT_SIZE)
    jersey_font = load_font(JERSEY_NUMBER_FONT_SIZE)
    stat_font = load_font(STAT_FONT_SIZE)

    draw.text(
        (PLAYER_NAME_X, PLAYER_NAME_Y),
        player_name.upper(),
        font=player_font,
        fill=PLAYER_NAME_COLOR,
    )
    draw.text(
        (TEAM_NAME_X, TEAM_NAME_Y),
        team_name.upper(),
        font=team_font,
        fill=TEAM_NAME_COLOR,
    )

    draw_centered_text(
        draw,
        JERSEY_NUMBER_CENTER_X,
        JERSEY_NUMBER_CENTER_Y,
        jersey_number,
        jersey_font,
        JERSEY_NUMBER_COLOR,
    )
    draw_centered_text(draw, SPEED_CENTER_X, SPEED_CENTER_Y, speed, stat_font, SPEED_COLOR)
    draw_centered_text(
        draw,
        SHOOTING_CENTER_X,
        SHOOTING_CENTER_Y,
        shooting,
        stat_font,
        SHOOTING_COLOR,
    )
    draw_centered_text(draw, PASSING_CENTER_X, PASSING_CENTER_Y, passing, stat_font, PASSING_COLOR)

    return card


# -----------------------------------------------------------------------------
# Image processing helpers
# -----------------------------------------------------------------------------
def read_input_image(uploaded_file) -> Image.Image:
    """Open a user-uploaded/camera image safely and normalize orientation/mode."""
    try:
        image = Image.open(uploaded_file)
        image.load()
        return image.convert("RGBA")
    except UnidentifiedImageError as exc:
        raise ValueError("The uploaded file is not a supported image.") from exc
    except Exception as exc:
        raise ValueError("Could not read the uploaded image. Try a different photo.") from exc


def remove_background(image: Image.Image) -> Image.Image:
    """Remove the photo background using rembg and return an RGBA cutout."""
    input_buffer = BytesIO()
    image.save(input_buffer, format="PNG")
    output_bytes = remove(input_buffer.getvalue())
    return Image.open(BytesIO(output_bytes)).convert("RGBA")


def alpha_bbox(image: Image.Image):
    """Return the visible alpha bounding box for an RGBA image."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getchannel("A").getbbox()


def crop_to_alpha(image: Image.Image, padding: int = 18) -> Image.Image:
    """Crop transparent margins around the player while preserving a small pad."""
    bbox = alpha_bbox(image)
    if not bbox:
        return image
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def clean_cutout_alpha(cutout: Image.Image) -> Image.Image:
    """Soften alpha edges and reduce white fringe without adding a backing layer."""
    cutout = cutout.convert("RGBA")
    r, g, b, a = cutout.split()

    # Slightly smooth the matte edge for a poster-like composite.
    a = a.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.GaussianBlur(radius=0.45))

    # Pull very bright edge pixels down a bit to reduce white halos from photos.
    rgb = Image.merge("RGB", (r, g, b))
    edge_mask = a.filter(ImageFilter.FIND_EDGES).point(lambda p: min(255, p * 3))
    darkened = ImageEnhance.Brightness(rgb).enhance(0.92)
    rgb = Image.composite(darkened, rgb, edge_mask)

    cleaned = Image.merge("RGBA", (*rgb.split(), a))
    return cleaned


def classify_shot(cutout: Image.Image) -> str:
    """Classify the cutout by visible aspect ratio for subject-aware sizing."""
    bbox = alpha_bbox(cutout)
    if not bbox:
        return "half_body"
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if height <= 0:
        return "half_body"

    aspect = width / height
    if aspect < 0.42:
        return "full_body"
    if aspect < 0.72:
        return "half_body"
    return "close_up"


def resize_player_for_zone(cutout: Image.Image) -> tuple[Image.Image, str]:
    """Resize player cutout according to shot type while respecting card zone width."""
    shot_type = classify_shot(cutout)
    target_height = {
        "full_body": FULL_BODY_TARGET_HEIGHT,
        "half_body": HALF_BODY_TARGET_HEIGHT,
        "close_up": CLOSE_UP_TARGET_HEIGHT,
    }[shot_type]

    scale = target_height / max(1, cutout.height)
    target_width = int(cutout.width * scale)

    zone_width = PLAYER_ZONE_X2 - PLAYER_ZONE_X1
    max_width = int(zone_width * 1.35)
    if target_width > max_width:
        scale = max_width / max(1, cutout.width)
        target_width = max_width
        target_height = int(cutout.height * scale)

    resized = cutout.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return resized, shot_type


def player_paste_position(player: Image.Image, shot_type: str) -> tuple[int, int]:
    """Anchor the player in the tuned zone without drawing any grey backing layer."""
    zone_center_x = (PLAYER_ZONE_X1 + PLAYER_ZONE_X2) // 2
    zone_bottom = PLAYER_ZONE_Y2

    x = int(zone_center_x - player.width / 2)

    if shot_type == "full_body":
        y = int(zone_bottom - player.height)
    elif shot_type == "half_body":
        y = int(zone_bottom - player.height + 22)
    else:
        y = int(PLAYER_ZONE_Y1 + 90)

    return x, y


def add_player_shadow(card: Image.Image, player: Image.Image, x: int, y: int) -> None:
    """Composite a soft shadow/glow derived from alpha only, not a rectangle."""
    alpha = player.getchannel("A")

    shadow = Image.new("RGBA", player.size, (0, 0, 0, 0))
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=18)).point(lambda p: int(p * 0.34))
    shadow.putalpha(shadow_alpha)
    card.alpha_composite(shadow, (x + 16, y + 20))

    glow = Image.new("RGBA", player.size, (255, 218, 94, 0))
    glow_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=10)).point(lambda p: int(p * 0.16))
    glow.putalpha(glow_alpha)
    card.alpha_composite(glow, (x - 4, y - 4))


def enhance_player(cutout: Image.Image) -> Image.Image:
    """Give the cutout a slightly punchier poster-card finish."""
    cutout = ImageEnhance.Contrast(cutout).enhance(1.08)
    cutout = ImageEnhance.Color(cutout).enhance(1.05)
    cutout = ImageEnhance.Sharpness(cutout).enhance(1.12)
    return cutout


def composite_foreground_splashes(card: Image.Image) -> None:
    """Optionally layer supplied foreground art over the player."""
    if not FOREGROUND_SPLASHES_PATH.exists():
        return
    try:
        overlay = Image.open(FOREGROUND_SPLASHES_PATH).convert("RGBA")
        overlay = overlay.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        card.alpha_composite(overlay, (0, 0))
    except Exception:
        # Foreground art is optional; never fail card generation because of it.
        return


def load_background() -> Image.Image:
    """Load the supplied static card template without regenerating it."""
    if BACKGROUND_PATH.exists():
        background = Image.open(BACKGROUND_PATH).convert("RGBA")
        if background.size != (CARD_WIDTH, CARD_HEIGHT):
            background = background.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        return background

    # Development fallback only: keeps the app usable before the final asset is added.
    fallback = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), "#F7E7B7")
    draw = ImageDraw.Draw(fallback)
    draw.rectangle((40, 40, CARD_WIDTH - 40, CARD_HEIGHT - 40), outline="#002B5C", width=8)
    draw.text((70, 70), "Add assets/background.png", fill="#002B5C", font=load_font(42))
    return fallback


# -----------------------------------------------------------------------------
# Optional OpenAI stylization
# -----------------------------------------------------------------------------
def stylize_player_with_openai(cutout: Image.Image) -> Image.Image:
    """
    Send only the cropped transparent player cutout to OpenAI for styling.
    The final card is never generated by OpenAI.
    """
    if OpenAI is None:
        raise RuntimeError("The openai package is not available.")

    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured in Streamlit secrets.")

    client = OpenAI(api_key=api_key)

    image_buffer = BytesIO()
    cutout.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    image_buffer.name = "player_cutout.png"

    prompt = (
        "Stylize this isolated transparent soccer player cutout only. "
        "Keep the same pose, body shape, uniform identity, and transparent background. "
        "Use watercolor texture, energetic ink sketch outlines, and a bold sports poster style. "
        "Do not add text, logos, card borders, fields, crowds, frames, or a complete trading card."
    )

    result = client.images.edit(
        model="gpt-image-1-mini",
        image=image_buffer,
        prompt=prompt,
        size="1024x1536",
    )

    b64_image = result.data[0].b64_json
    styled_bytes = base64.b64decode(b64_image)
    styled = Image.open(BytesIO(styled_bytes)).convert("RGBA")

    # Crop again because image models may add extra transparent/empty space.
    return crop_to_alpha(styled, padding=12)


def prepare_player_cutout(source_image: Image.Image, use_ai_style: bool) -> Image.Image:
    """Run rembg first, then optionally AI-stylize the cropped cutout."""
    cutout = remove_background(source_image)
    cutout = crop_to_alpha(cutout, padding=18)
    cutout = clean_cutout_alpha(cutout)

    if not use_ai_style:
        return cutout

    try:
        with st.spinner("Applying AI artistic style to player cutout…"):
            styled = stylize_player_with_openai(cutout)
            styled = clean_cutout_alpha(styled)
            return styled
    except Exception as exc:
        st.warning(f"AI styling failed, so the normal cutout was used instead. ({exc})")
        return cutout


# -----------------------------------------------------------------------------
# Card generation
# -----------------------------------------------------------------------------
def generate_card(
    source_image: Image.Image,
    player_name: str,
    team_name: str,
    jersey_number: str,
    speed: int,
    shooting: int,
    passing: int,
    use_ai_style: bool,
) -> Image.Image:
    """Create the final card with Pillow compositing and text rendering."""
    card = load_background()

    player_cutout = prepare_player_cutout(source_image, use_ai_style=use_ai_style)
    player_cutout = enhance_player(player_cutout)
    player_resized, shot_type = resize_player_for_zone(player_cutout)
    x, y = player_paste_position(player_resized, shot_type)

    add_player_shadow(card, player_resized, x, y)
    card.alpha_composite(player_resized, (x, y))
    composite_foreground_splashes(card)

    draw_card_text(
        card,
        player_name=player_name,
        team_name=team_name,
        jersey_number=jersey_number,
        speed=speed,
        shooting=shooting,
        passing=passing,
    )

    return card.convert("RGB")


def image_to_png_bytes(image: Image.Image) -> bytes:
    """Serialize a Pillow image to PNG bytes for Streamlit download."""
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
with st.form("card_inputs"):
    player_name = st.text_input("Player Name", value="Alex Morgan")
    team_name = st.text_input("Team Name", value="CSC United")
    jersey_number = st.text_input("Jersey Number", value="10", max_chars=3)

    col1, col2, col3 = st.columns(3)
    with col1:
        speed = st.slider("Speed", 0, 99, 88)
    with col2:
        shooting = st.slider("Shooting", 0, 99, 91)
    with col3:
        passing = st.slider("Passing", 0, 99, 84)

    use_ai_style = st.checkbox(
        "Use AI artistic style",
        value=False,
        help=(
            "Optional. Uses rembg first, then sends only the transparent player cutout "
            "to OpenAI for watercolor + ink sports-poster styling."
        ),
    )

    st.markdown("### Player photo")
    camera_photo = st.camera_input("Take a player photo")
    uploaded_photo = st.file_uploader(
        "Or upload a player photo",
        type=["png", "jpg", "jpeg", "webp"],
    )

    submitted = st.form_submit_button("Generate card", type="primary")

selected_photo = camera_photo or uploaded_photo

if submitted:
    if not player_name.strip():
        st.error("Enter a player name.")
    elif not team_name.strip():
        st.error("Enter a team name.")
    elif not jersey_number.strip():
        st.error("Enter a jersey number.")
    elif selected_photo is None:
        st.error("Take or upload a player photo.")
    else:
        try:
            source = read_input_image(selected_photo)
            with st.spinner("Generating card…"):
                final_card = generate_card(
                    source_image=source,
                    player_name=player_name.strip(),
                    team_name=team_name.strip(),
                    jersey_number=jersey_number.strip(),
                    speed=speed,
                    shooting=shooting,
                    passing=passing,
                    use_ai_style=use_ai_style,
                )

            st.success("Card generated.")
            st.image(final_card, caption="Final card preview", use_container_width=True)

            png_bytes = image_to_png_bytes(final_card)
            safe_name = "_".join(player_name.strip().lower().split()) or "player"
            st.download_button(
                "Download PNG",
                data=png_bytes,
                file_name=f"{safe_name}_csc_card.png",
                mime="image/png",
            )
        except RuntimeError as exc:
            st.error(str(exc))
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Card generation failed. Try another photo. ({exc})")
else:
    st.info("Enter player details, add a photo, then generate the card.")
    if BACKGROUND_PATH.exists():
        try:
            preview_bg = load_background().convert("RGB")
            st.image(preview_bg, caption="Current background template", use_container_width=True)
        except Exception:
            pass
