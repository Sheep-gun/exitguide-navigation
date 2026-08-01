from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "apps" / "mobile" / "assets"
ICON_SIZE = 1024

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def font(size: int) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def draw_icon(path: Path, with_safe_padding: bool) -> None:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), "#F6F8FB")
    draw = ImageDraw.Draw(image)
    margin = 180 if with_safe_padding else 128
    shield = (
        margin,
        margin,
        ICON_SIZE - margin,
        ICON_SIZE - margin,
    )
    draw.rounded_rectangle(shield, radius=170, fill="#2B6F68")
    draw.rounded_rectangle(
        (shield[0] + 70, shield[1] + 70, shield[2] - 70, shield[3] - 70),
        radius=120,
        outline="#EAF5F2",
        width=26,
    )

    text_font = font(236 if with_safe_padding else 286)
    text = "EG"
    box = draw.textbbox((0, 0), text, font=text_font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    draw.text(
        ((ICON_SIZE - text_width) / 2, (ICON_SIZE - text_height) / 2 - 24),
        text,
        font=text_font,
        fill="#FFFFFF",
    )
    image.save(path)


def draw_splash(path: Path) -> None:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), "#F6F8FB")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((282, 282, 742, 742), radius=120, fill="#2B6F68")
    draw.rounded_rectangle((342, 342, 682, 682), radius=90, outline="#EAF5F2", width=20)
    text_font = font(170)
    text = "EG"
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text(
        ((ICON_SIZE - (box[2] - box[0])) / 2, (ICON_SIZE - (box[3] - box[1])) / 2 - 18),
        text,
        font=text_font,
        fill="#FFFFFF",
    )
    image.save(path)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    draw_icon(ASSETS / "icon.png", with_safe_padding=False)
    draw_icon(ASSETS / "adaptive-icon.png", with_safe_padding=True)
    draw_splash(ASSETS / "splash-icon.png")
    print(f"generated mobile assets in {ASSETS}")


if __name__ == "__main__":
    main()
