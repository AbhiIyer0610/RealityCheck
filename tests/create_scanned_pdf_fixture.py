from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


FIXTURE_DIR = Path(__file__).parent / "fixtures"
OUTPUT_PATH = FIXTURE_DIR / "scanned_refund_policy.pdf"

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
SENTENCE = "Scanned policy: refunds are allowed within 30 days."


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1600, 500), "white")
    draw = ImageDraw.Draw(image)

    font_candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]

    font = None
    for font_path in font_candidates:
        if Path(font_path).exists():
            font = ImageFont.truetype(font_path, 48)
            break

    if font is None:
        font = ImageFont.load_default(size=48)

    draw.text((60, 150), SENTENCE, fill="black", font=font)

    image_path = FIXTURE_DIR / "scanned_refund_policy.png"
    image.save(image_path, dpi=(200, 200))

    pdf = canvas.Canvas(str(OUTPUT_PATH), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.drawImage(
        ImageReader(image_path),
        40,
        300,
        width=PAGE_WIDTH - 80,
        height=180,
        preserveAspectRatio=True,
        anchor="c",
    )
    pdf.save()

    image_path.unlink(missing_ok=True)
    print(f"Created scanned PDF fixture: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()