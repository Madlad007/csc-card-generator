import base64
import io
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from rembg import remove


CARD_WIDTH = 1080
CARD_HEIGHT = 1350

BACKGROUND_PATH = Path("assets/background.png")
FOREGROUND_SPLASH_PATH = Path("assets/foreground_splashes.png")

PLAYER_ZONE_X1 = 390
PLAYER_ZONE_Y1 = 160
PLAYER_ZONE_X2 = 740
PLAYER_ZONE_Y2 = 1120

FULL_BODY_TARGET_HEIGHT = 1050
HALF_BODY_TARGET_HEIGHT = 980
CLOSE_UP_TARGET_HEIGHT = 900

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

FONT_CANDIDATES = [
    "assets/fonts/brush.ttf",
    "assets/fonts/BebasNeue-Regular.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

AI_STYLE_PROMPT = """
You are an expert sports illustrator and digital artist.

Transform the provided background-removed soccer player cutout into a hyper-detailed sketch + watercolor sports portrait.

Create a WAIST-UP or MID-THIGH-UP composition only. The player must appear large, dominant, and poster-worthy, not small or full-body.

Composition rules:
- Crop the artwork from roughly waist or mid-thigh upward.
- Keep the player centered.
- Make the face and upper body large and prominent.
- The final player artwork should fill most of the vertical canvas.
- Preserve the player’s identity, face, hairstyle, beard, skin tone, expression, jersey, pose, and body proportions.
- Do not change the player into a different person.

Style rules:
- Use hand-drawn ink sketch lines.
- Add watercolor paint textures, splashes, ink drops, rough energetic strokes, and subtle grunge detail.
- Use the jersey/team colors naturally in the paint splashes.
- Make it look like a premium sports poster illustration.

Output rules:
- Return only the artistic player cutout.
- Transparent background outside the player and paint splashes.
- No white rectangle.
- No card layout.
- No text.
- No names.
- No numbers.
- No logos.
- No badges.
- No shadows.
- No watermark.
"""


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue

    for bundled_name in ("DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(bundled_name, size=size)
        except OSError:
            continue

    raise RuntimeError("No usable TrueType font found. Add assets/fonts/brush.ttf.")


def open_image_from_input(image_file) -> Image.Image:
    image_file.seek(0)
    image = Image.open(image_file)
    image = ImageOps.exif_transpose(image)
    return image.convert("RGBA")


def alpha_bounds(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getchannel("A").getbbox()


def crop_transparent_cutout(image: Image.Image, padding: int = 24) -> Image.Image:
    bounds = alpha_bounds(image)
    if not bounds:
        return image.convert("RGBA")

    left, top, right, bottom = bounds
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom)).convert("RGBA")


def clean_cutout(cutout: Image.Image) -> Image.Image:
    cutout = cutout.convert("RGBA")
    r, g, b, a = cutout.split()

    a = a.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.GaussianBlur(radius=0.35))

    rgb = Image.merge("RGB", (r, g, b))
    rgb = ImageEnhance.Color(rgb).enhance(1.08)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.08)

    cleaned = Image.merge("RGBA", (*rgb.split(), a))
    return crop_transparent_cutout(cleaned, padding=18)


def remove_player_background(image: Image.Image) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    removed_bytes = remove(buffer.getvalue())
    cutout = Image.open(io.BytesIO(removed_bytes)).convert("RGBA")
    return clean_cutout(cutout)


def classify_player_shot(cutout: Image.Image) -> str:
    bounds = alpha_bounds(cutout)
    if not bounds:
        return "half_body"

    left, top, right, bottom = bounds
    visible_width = max(1, right - left)
    visible_height = max(1, bottom - top)
    ratio = visible_height / visible_width

    if ratio >= 2.25:
        return "full_body"
    if ratio >= 1.45:
        return "half_body"
    return "close_up"


def resize_player_for_zone(cutout: Image.Image) -> Tuple[Image.Image, str]:
    shot_type = classify_player_shot(cutout)

    target_height = {
        "full_body": FULL_BODY_TARGET_HEIGHT,
        "half_body": HALF_BODY_TARGET_HEIGHT,
        "close_up": CLOSE_UP_TARGET_HEIGHT,
    }[shot_type]

    scale = target_height / max(1, cutout.height)
    new_width = max(1, int(cutout.width * scale))
    new_height = max(1, int(cutout.height * scale))

    zone_width = PLAYER_ZONE_X2 - PLAYER_ZONE_X1
    if new_width > zone_width * 1.22:
        scale = (zone_width * 1.22) / max(1, cutout.width)
        new_width = max(1, int(cutout.width * scale))
        new_height = max(1, int(cutout.height * scale))

    resized = cutout.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return resized, shot_type


def paste_player_with_blend(card: Image.Image, cutout: Image.Image) -> Image.Image:
    player, shot_type = resize_player_for_zone(cutout)

    zone_width = PLAYER_ZONE_X2 - PLAYER_ZONE_X1
    zone_height = PLAYER_ZONE_Y2 - PLAYER_ZONE_Y1

    x = int(PLAYER_ZONE_X1 + (zone_width - player.width) / 2)

    if shot_type == "full_body":
        y = int(PLAYER_ZONE_Y2 - player.height)
    elif shot_type == "half_body":
        y = int(PLAYER_ZONE_Y1 + zone_height * 0.28)
    else:
        y = int(PLAYER_ZONE_Y1 + zone_height * 0.2)

    x = max(0, min(CARD_WIDTH - player.width, x))
    y = max(0, min(CARD_HEIGHT - player.height, y))

    card.alpha_composite(player, (x, y))
    return card


def apply_optional_foreground(card: Image.Image) -> Image.Image:
    if not FOREGROUND_SPLASH_PATH.exists():
        return card

    foreground = Image.open(FOREGROUND_SPLASH_PATH).convert("RGBA")
    if foreground.size != card.size:
        foreground = foreground.resize(card.size, Image.Resampling.LANCZOS)

    return Image.alpha_composite(card, foreground)


def draw_centered_text(draw, center_x, center_y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = center_x - width / 2 - bbox[0]
    y = center_y - height / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def draw_card_text(card, player_name, team_name, jersey_number, speed, shooting, passing):
    draw = ImageDraw.Draw(card)

    name_font = load_font(PLAYER_NAME_FONT_SIZE)
    team_font = load_font(TEAM_NAME_FONT_SIZE)
    jersey_font = load_font(JERSEY_NUMBER_FONT_SIZE)
    stat_font = load_font(STAT_FONT_SIZE)

    draw.text((PLAYER_NAME_X, PLAYER_NAME_Y), player_name.upper(), font=name_font, fill=PLAYER_NAME_COLOR)
    draw.text((TEAM_NAME_X, TEAM_NAME_Y), team_name.upper(), font=team_font, fill=TEAM_NAME_COLOR)

    draw_centered_text(draw, JERSEY_NUMBER_CENTER_X, JERSEY_NUMBER_CENTER_Y, str(jersey_number), jersey_font, JERSEY_NUMBER_COLOR)
    draw_centered_text(draw, SPEED_CENTER_X, SPEED_CENTER_Y, str(speed), stat_font, SPEED_COLOR)
    draw_centered_text(draw, SHOOTING_CENTER_X, SHOOTING_CENTER_Y, str(shooting), stat_font, SHOOTING_COLOR)
    draw_centered_text(draw, PASSING_CENTER_X, PASSING_CENTER_Y, str(passing), stat_font, PASSING_COLOR)

    return card


def get_openai_api_key() -> Optional[str]:
    try:
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:
        return None


def stylize_cutout_with_openai(cutout: Image.Image) -> Image.Image:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured in Streamlit secrets.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the openai package to enable AI artistic style.") from exc

    cropped = crop_transparent_cutout(cutout, padding=32)

    image_buffer = io.BytesIO()
    cropped.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    image_buffer.name = "player_cutout.png"

    client = OpenAI(api_key=api_key)

    result = client.images.edit(
        model="gpt-image-1-mini",
        image=image_buffer,
        prompt=AI_STYLE_PROMPT,
        size="1024x1536",
        background="transparent",
        n=1,
    )

    image_data = result.data[0]
    b64_image = getattr(image_data, "b64_json", None)

    if not b64_image:
        raise RuntimeError("OpenAI did not return image data.")

    stylized_bytes = base64.b64decode(b64_image)
    stylized = Image.open(io.BytesIO(stylized_bytes)).convert("RGBA")

    return clean_cutout(stylized)


def prepare_player_cutout(source_image: Image.Image, use_ai_style: bool):
    rembg_cutout = remove_player_background(source_image)

    if not use_ai_style:
        return rembg_cutout, False, None

    try:
        stylized = stylize_cutout_with_openai(rembg_cutout)
        return stylized, True, None
    except Exception as exc:
        return rembg_cutout, False, str(exc)


def build_card(source_image, player_name, team_name, jersey_number, speed, shooting, passing, use_ai_style):
    if not BACKGROUND_PATH.exists():
        raise FileNotFoundError("Missing assets/background.png.")

    background = Image.open(BACKGROUND_PATH).convert("RGBA")
    if background.size != (CARD_WIDTH, CARD_HEIGHT):
        background = background.resize((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)

    cutout, ai_used, ai_error = prepare_player_cutout(source_image, use_ai_style)

    card = paste_player_with_blend(background, cutout)
    card = apply_optional_foreground(card)
    card = draw_card_text(card, player_name, team_name, jersey_number, speed, shooting, passing)

    return card, ai_used, ai_error


def image_to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def main():
    st.set_page_config(page_title="CSC Tournament Card Generator", page_icon="⚽", layout="centered")

    st.title("CSC Tournament Card Generator")
    st.caption("Create a 1080×1350 tournament trading card from a camera or uploaded player photo.")

    with st.form("card_form"):
        player_name = st.text_input("Player Name", value="", placeholder="Enter player name")
        team_name = st.text_input("Team Name", value="", placeholder="Enter team name")
        jersey_number = st.text_input("Jersey Number", value="10", max_chars=3)

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            speed = st.slider("Speed", min_value=1, max_value=99, value=88)
        with col_b:
            shooting = st.slider("Shooting", min_value=1, max_value=99, value=84)
        with col_c:
            passing = st.slider("Passing", min_value=1, max_value=99, value=82)

        use_ai_style = st.checkbox(
            "Use AI artistic style",
            value=False,
            help="Uses OpenAI to stylize only the background-removed player cutout. If it fails, the normal free version is used.",
        )

        st.subheader("Player photo")

        camera_photo = st.camera_input("Take a photo")
        uploaded_photo = st.file_uploader(
            "Or upload a player photo",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=False,
        )

        submitted = st.form_submit_button("Generate card", type="primary", use_container_width=True)

    selected_photo = camera_photo or uploaded_photo

    if submitted:
        if not player_name.strip() or not team_name.strip() or not jersey_number.strip():
            st.error("Please enter player name, team name, and jersey number.")
            return

        if selected_photo is None:
            st.error("Please take or upload a player photo.")
            return

        try:
            source_image = open_image_from_input(selected_photo)

            with st.spinner("Generating your card..."):
                card, ai_used, ai_error = build_card(
                    source_image=source_image,
                    player_name=player_name.strip(),
                    team_name=team_name.strip(),
                    jersey_number=jersey_number.strip(),
                    speed=speed,
                    shooting=shooting,
                    passing=passing,
                    use_ai_style=use_ai_style,
                )

            if use_ai_style and ai_used:
                st.success("AI artistic player style applied.")
            elif use_ai_style and ai_error:
                st.warning(f"AI style failed, so the normal cutout was used. Details: {ai_error}")

            png_bytes = image_to_png_bytes(card)

            st.image(png_bytes, caption="Generated CSC tournament card", use_container_width=True)

            st.download_button(
                "Download PNG",
                data=png_bytes,
                file_name=f"csc-card-{player_name.strip().lower().replace(' ', '-')}.png",
                mime="image/png",
                use_container_width=True,
            )

        except Exception as exc:
            st.error(f"Could not generate the card: {exc}")


if __name__ == "__main__":
    main()
