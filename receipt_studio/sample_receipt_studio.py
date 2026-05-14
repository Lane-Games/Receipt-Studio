from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageTk


APP_TITLE = "Prop Receipt Studio"
SAFE_NOTICE = "PROP RECEIPT - NOT VALID"

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
else:
    ROOT_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = ROOT_DIR
OUTPUT_DIR = ROOT_DIR / "exports"
ASSET_DIRS = [RESOURCE_DIR / "assets", ROOT_DIR / "assets", Path("C:/Users/turnn/Downloads/Assets")]


STORE_TEMPLATES: dict[str, dict[str, Any]] = {
    "target": {
        "label": "Target style",
        "display_name": "TARGET",
        "location": "Memphis East - 5959 Poplar Ave, Memphis, TN",
        "phone": "901-261-5079",
        "store_no": "T-1024",
        "register": "02",
        "cashier": "TEAM MEMBER",
        "tax_rate": "9.75",
        "payment": "VISA",
        "card_last4": "5025",
        "section": "GROCERY",
        "footer": [
            "Your Target Circle earnings are in.",
            "Open the app to see your benefits.",
        ],
    },
    "walmart": {
        "label": "Walmart style",
        "display_name": "Walmart",
        "location": "3451 Truxel Rd, Sacramento, CA",
        "phone": "916-968-2258",
        "store_no": "0023",
        "register": "01234",
        "cashier": "ASSOCIATE",
        "tax_rate": "8.00",
        "payment": "DEBIT",
        "card_last4": "8867",
        "section": "GENERAL MERCHANDISE",
        "footer": [
            "Low prices you can trust. Every day.",
            "Store receipts on your phone.",
        ],
    },
    "cvs": {
        "label": "CVS style",
        "display_name": "CVS/pharmacy",
        "location": "123 Health Way, Providence, RI",
        "phone": "401-555-0198",
        "store_no": "C-314",
        "register": "04",
        "cashier": "CASHIER",
        "tax_rate": "7.00",
        "payment": "VISA",
        "card_last4": "1234",
        "section": "FRONT STORE",
        "footer": [
            "ExtraCare offers",
            "Coupons printed below: 0",
        ],
    },
    "costco": {
        "label": "Costco style",
        "display_name": "COSTCO WHOLESALE",
        "location": "456 Warehouse Ln, Seattle, WA",
        "phone": "206-555-0182",
        "store_no": "WH-071",
        "register": "07",
        "cashier": "OPERATOR",
        "tax_rate": "10.10",
        "payment": "MASTERCARD",
        "card_last4": "7777",
        "section": "WAREHOUSE",
        "footer": [
            "Member savings applied where eligible.",
            "Thank you for shopping.",
        ],
    },
}

STORE_ORDER = ["target", "walmart", "cvs", "costco"]

AI_IMPORT_PROMPT = """You are converting shopping information into JSON for a safe prop receipt app.
Return only valid JSON. Do not include markdown, comments, or explanations.

Use this schema:
{
  "store": "target | walmart | cvs | costco",
  "display_name": "optional display name for the mock receipt",
  "location": "single-line store location",
  "phone": "optional phone",
  "date": "YYYY-MM-DD",
  "time": "HH:MM AM/PM",
  "store_no": "optional store number",
  "register": "optional register number",
  "cashier": "optional cashier name",
  "transaction_id": "optional transaction id",
  "tax_rate_percent": 8.25,
  "payment_method": "VISA | DEBIT | CASH | MASTERCARD | OTHER",
  "card_last4": "optional last 4 digits",
  "items": [
    {
      "upc": "optional UPC/SKU text",
      "description": "item name",
      "quantity": 1,
      "unit_price": 3.99,
      "taxable": true,
      "category": "optional category"
    }
  ]
}

Rules:
- Use numbers for quantity, unit_price, and tax_rate_percent.
- If the tax rate is unknown, estimate from the location and set tax_rate_percent.
- If a field is unknown, use an empty string instead of inventing official-looking data.
- Keep descriptions short enough for a narrow receipt line.
- This is for a PROP / NOT VALID receipt only.
"""


@dataclass
class ReceiptItem:
    upc: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    taxable: bool = True
    category: str = ""

    @property
    def total(self) -> Decimal:
        return money(self.quantity * self.unit_price)


def money(value: Decimal | int | float | str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        decimal_value = Decimal("0")
    return decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value: Decimal | int | float | str) -> str:
    amount = money(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    return f"{sign}${amount:,.2f}"


def fmt_qty(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def decimal_from_text(value: str, fallback: str = "0") -> Decimal:
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal(fallback)


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_time() -> str:
    return datetime.now().strftime("%I:%M %p")


def stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
    return int(digest[:12], 16)


class ReceiptRenderer:
    def __init__(self) -> None:
        self.font_regular = self._font(["consola.ttf", "cour.ttf", "lucon.ttf"], 23)
        self.font_small = self._font(["consola.ttf", "cour.ttf", "lucon.ttf"], 18)
        self.font_tiny = self._font(["consola.ttf", "cour.ttf", "lucon.ttf"], 15)
        self.font_bold = self._font(["consolab.ttf", "courbd.ttf", "arialbd.ttf"], 24)
        self.font_title = self._font(["arialbd.ttf", "segoeuib.ttf", "consolab.ttf"], 45)
        self.font_brand = self._font(["arialbd.ttf", "segoeuib.ttf", "arial.ttf"], 62)
        self.font_notice = self._font(["arialbd.ttf", "segoeuib.ttf", "arial.ttf"], 17)
        self.assets = self._build_assets()

    def _font(self, candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_dirs = [
            Path("C:/Windows/Fonts"),
            ROOT_DIR / "fonts",
            RESOURCE_DIR / "fonts",
        ]
        for directory in font_dirs:
            for candidate in candidates:
                path = directory / candidate
                if path.exists():
                    return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()

    def _build_assets(self) -> dict[str, Image.Image | dict[str, Image.Image]]:
        return {
            "wood": self._load_asset("woodBG.png") or self._make_wood_texture(),
            "paper": self._load_asset("PaperTexture.png") or self._make_crumpled_paper_texture(),
            "grime": self._load_asset("TransparentGrime.png") or self._make_grime_overlay(),
            "logos": {
                "target": self._load_asset("Target.png") or self._make_target_logo(),
                "walmart": self._load_asset("Walmart.png") or self._make_walmart_logo(),
                "cvs": self._load_asset("CVS.png") or self._make_cvs_logo(),
                "costco": self._load_asset("Costco.png") or self._make_costco_logo(),
            },
        }

    def _load_asset(self, name: str) -> Image.Image | None:
        for directory in ASSET_DIRS:
            path = directory / name
            if path.exists():
                try:
                    return Image.open(path).convert("RGBA")
                except OSError:
                    continue
        return None

    def _make_wood_texture(self) -> Image.Image:
        width, height = 2048, 1152
        rng = random.Random(4126)
        base_noise = Image.effect_noise((width, height), 44).convert("L")
        base_noise = base_noise.filter(ImageFilter.GaussianBlur((4, 0)))
        wood = ImageOps.colorize(base_noise, black=(34, 19, 10), white=(126, 76, 34)).convert("RGBA")
        draw = ImageDraw.Draw(wood, "RGBA")
        for y in range(0, height, 280):
            draw.rectangle((0, y - 2, width, y + 4), fill=(18, 10, 6, 115))
            draw.line((0, y + 12, width, y + 9), fill=(164, 107, 54, 42), width=2)
        for _ in range(480):
            y = rng.randrange(height)
            x = rng.randrange(-100, width)
            length = rng.randrange(240, 920)
            color = rng.choice([(14, 9, 5, 95), (190, 128, 65, 40), (86, 50, 23, 70)])
            draw.line((x, y, min(width, x + length), y + rng.randrange(-5, 6)), fill=color, width=rng.choice([1, 1, 2]))
        for _ in range(36):
            x = rng.randrange(width)
            y = rng.randrange(height)
            radius = rng.randrange(30, 95)
            draw.ellipse((x - radius, y - radius // 3, x + radius, y + radius // 3), outline=(18, 12, 8, 70), width=2)
        return wood.filter(ImageFilter.UnsharpMask(radius=1.4, percent=135, threshold=3))

    def _make_crumpled_paper_texture(self) -> Image.Image:
        width, height = 900, 1500
        rng = random.Random(8185)
        base = Image.new("L", (width, height), 232)
        large = Image.effect_noise((width, height), 18).convert("L").filter(ImageFilter.GaussianBlur(3.5))
        fine = Image.effect_noise((width, height), 8).convert("L")
        base = Image.blend(base, large, 0.20)
        base = Image.blend(base, fine, 0.08)
        folds = Image.new("L", (width, height), 128)
        fd = ImageDraw.Draw(folds)
        for _ in range(42):
            x1 = rng.randrange(-80, width + 80)
            y1 = rng.randrange(-80, height + 80)
            length = rng.randrange(320, 980)
            angle = rng.uniform(-1.0, 1.0)
            x2 = int(x1 + math.cos(angle) * length)
            y2 = int(y1 + math.sin(angle) * length)
            shade = rng.choice([55, 72, 180, 205])
            fd.line((x1, y1, x2, y2), fill=shade, width=rng.choice([1, 2, 3, 5]))
            fd.line((x1 + 5, y1 + 3, x2 + 5, y2 + 3), fill=190 if shade < 128 else 82, width=1)
        folds = folds.filter(ImageFilter.GaussianBlur(4))
        paper = ImageChops.multiply(base, ImageOps.colorize(folds, black=198, white=255).convert("L"))
        paper = ImageEnhance.Contrast(paper).enhance(1.10)
        paper = ImageOps.colorize(paper, black=(198, 198, 193), white=(255, 255, 252)).convert("RGBA")
        return paper

    def _make_grime_overlay(self) -> Image.Image:
        width, height = 900, 1500
        rng = random.Random(2209)
        noise = Image.effect_noise((width, height), 58).convert("L")
        cracks = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(cracks)
        for _ in range(90):
            x = rng.randrange(width)
            y = rng.randrange(height)
            points = [(x, y)]
            for _step in range(rng.randrange(3, 8)):
                x += rng.randrange(-70, 71)
                y += rng.randrange(-36, 37)
                points.append((x, y))
            draw.line(points, fill=rng.randrange(18, 58), width=rng.choice([1, 1, 2]))
        soft = ImageChops.screen(noise.point(lambda p: max(0, p - 142)), cracks)
        alpha = soft.point(lambda p: min(78, int(p * 0.42)))
        overlay = Image.new("RGBA", (width, height), (18, 17, 15, 0))
        overlay.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))
        return overlay

    def _make_target_logo(self) -> Image.Image:
        image = Image.new("RGBA", (520, 260), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cx, cy = 260, 78
        draw.ellipse((cx - 58, cy - 58, cx + 58, cy + 58), outline=(0, 0, 0, 255), width=18)
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(0, 0, 0, 255))
        self._center_on_image(draw, "TARGET", image.size[0], 150, self.font_brand)
        return image

    def _make_walmart_logo(self) -> Image.Image:
        image = Image.new("RGBA", (720, 220), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        text = "Walmart"
        bbox = draw.textbbox((0, 0), text, font=self.font_brand)
        draw.text((40, 42), text, font=self.font_brand, fill=(0, 0, 0, 255))
        spark_cx = 40 + (bbox[2] - bbox[0]) + 50
        spark_cy = 78
        for angle in range(0, 360, 60):
            radians = math.radians(angle)
            x1 = spark_cx + math.cos(radians) * 11
            y1 = spark_cy + math.sin(radians) * 11
            x2 = spark_cx + math.cos(radians) * 29
            y2 = spark_cy + math.sin(radians) * 29
            draw.line((x1, y1, x2, y2), fill=(0, 0, 0, 255), width=8)
        draw.text((74, 128), "Save money. Live better.", font=self.font_small, fill=(0, 0, 0, 255))
        return image

    def _make_cvs_logo(self) -> Image.Image:
        image = Image.new("RGBA", (650, 190), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        hx, hy = 40, 42
        draw.ellipse((hx, hy, hx + 42, hy + 42), fill=(0, 0, 0, 255))
        draw.ellipse((hx + 32, hy, hx + 74, hy + 42), fill=(0, 0, 0, 255))
        draw.polygon([(hx + 2, hy + 28), (hx + 72, hy + 28), (hx + 37, hy + 86)], fill=(0, 0, 0, 255))
        draw.text((138, 38), "CVS/pharmacy", font=self.font_brand, fill=(0, 0, 0, 255))
        return image

    def _make_costco_logo(self) -> Image.Image:
        image = Image.new("RGBA", (760, 220), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text((24, 28), "COSTCO", font=self.font_brand, fill=(0, 0, 0, 255))
        draw.line((28, 110, 405, 110), fill=(0, 0, 0, 255), width=7)
        draw.line((28, 126, 365, 126), fill=(0, 0, 0, 255), width=5)
        draw.text((305, 112), "WHOLESALE", font=self.font_bold, fill=(0, 0, 0, 255))
        return image

    def _center_on_image(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        width: int,
        y: int,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int, int] = (0, 0, 0, 255),
    ) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), text, font=font, fill=fill)

    def render_receipt(self, data: dict[str, Any], items: list[ReceiptItem]) -> Image.Image:
        store_key = data.get("store", "target")
        template = STORE_TEMPLATES.get(store_key, STORE_TEMPLATES["target"])
        seed_text = json.dumps(data, sort_keys=True, default=str) + "".join(
            f"{i.upc}{i.description}{i.quantity}{i.unit_price}" for i in items
        )
        rng = random.Random(stable_seed(seed_text))

        width = 620
        estimated_height = max(1800, 1250 + len(items) * 95 + len(template["footer"]) * 45)
        paper = self._paper_texture(width, estimated_height, rng)
        draw = ImageDraw.Draw(paper)

        margin = 36
        right = width - margin
        y = 34

        y = self._notice_bar(draw, margin, right, y)
        y = self._draw_logo(paper, draw, store_key, data.get("display_name") or template["display_name"], y, width)

        header_lines = [
            data.get("location") or template["location"],
            data.get("phone") or template["phone"],
            f"STORE {data.get('store_no') or template['store_no']}  REG {data.get('register') or template['register']}",
            f"CASHIER {data.get('cashier') or template['cashier']}",
        ]
        for line in header_lines:
            y = self._center(draw, line, y, self.font_regular, fill=(24, 24, 24), max_width=right - margin)
        y += 18

        date_text = data.get("date") or now_date()
        time_text = data.get("time") or now_time()
        self._lr(draw, f"DATE: {date_text}", f"TIME: {time_text}", margin, right, y, self.font_regular)
        y += 44

        if store_key in {"target", "walmart"}:
            y = self._fake_barcode(draw, margin + 78, right - 78, y, height=74, seed=seed_text)
            y += 20

        y = self._rule(draw, margin, right, y)
        y += 15

        section = data.get("section") or template["section"]
        draw.text((margin, y), section.upper(), font=self.font_bold, fill=(18, 18, 18))
        y += 40

        if not items:
            y = self._center(draw, "No items added yet", y, self.font_regular, fill=(85, 85, 85))
            y += 20
        else:
            for item in items:
                y = self._draw_item(draw, item, margin, right, y)

        subtotal = sum((item.total for item in items), Decimal("0.00"))
        taxable_subtotal = sum((item.total for item in items if item.taxable), Decimal("0.00"))
        tax_rate = decimal_from_text(str(data.get("tax_rate_percent") or template["tax_rate"]))
        tax = money(taxable_subtotal * (tax_rate / Decimal("100")))
        total = money(subtotal + tax)

        y += 12
        y = self._rule(draw, margin, right, y)
        y += 18
        self._lr(draw, "SUBTOTAL", fmt_money(subtotal), margin, right, y, self.font_bold)
        y += 38
        self._lr(draw, f"TAX ({tax_rate.normalize()}%)", fmt_money(tax), margin, right, y, self.font_regular)
        y += 34
        self._lr(draw, "TOTAL", fmt_money(total), margin, right, y, self.font_bold)
        y += 58

        payment_method = str(data.get("payment_method") or template["payment"]).upper()
        card_last4 = str(data.get("card_last4") or template["card_last4"]).strip()
        txn = str(data.get("transaction_id") or self._transaction_id(seed_text))
        if payment_method == "CASH":
            self._lr(draw, "CASH TEND", fmt_money(total), margin, right, y, self.font_regular)
            y += 32
            self._lr(draw, "CHANGE DUE", "$0.00", margin, right, y, self.font_regular)
        else:
            masked = f"**** {card_last4}" if card_last4 else "****"
            self._lr(draw, f"{payment_method} TEND", fmt_money(total), margin, right, y, self.font_regular)
            y += 32
            draw.text((margin, y), f"{payment_method} {masked}", font=self.font_regular, fill=(22, 22, 22))
        y += 35
        draw.text((margin, y), f"TRANS ID: {txn}", font=self.font_regular, fill=(22, 22, 22))
        y += 40
        draw.text((margin, y), f"AUTH CODE: {self._auth_code(seed_text)}", font=self.font_regular, fill=(22, 22, 22))
        y += 50

        for line in template["footer"]:
            y = self._center(draw, line, y, self.font_regular, fill=(22, 22, 22), max_width=right - margin)
        y += 14
        y = self._rule(draw, margin, right, y)
        y += 24
        y = self._center(draw, f"# ITEMS SOLD {len(items)}", y, self.font_bold, fill=(10, 10, 10))
        y += 20

        if store_key in {"walmart", "cvs"}:
            y = self._fake_qr(draw, width // 2 - 72, y + 8, 144, seed_text)
            y += 28
        else:
            y = self._fake_barcode(draw, margin + 24, right - 24, y + 10, height=68, seed=seed_text[::-1])
            y += 34

        y += 64

        final = paper.crop((0, 0, width, min(y, paper.height)))
        return final

    def compose_scene(
        self,
        receipt: Image.Image,
        background: str,
        viewport: tuple[int, int] | None = None,
        center_receipt: bool = False,
        fixed_viewport: bool = False,
    ) -> Image.Image:
        pad_x = 180
        pad_y = 110
        receipt_layer = self._bend_receipt_layer(receipt.convert("RGBA")).rotate(
            -1.15,
            expand=True,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        if viewport and fixed_viewport:
            width, height = viewport
        else:
            width = max(receipt_layer.width + pad_x * 2, 920)
            height = max(receipt_layer.height + pad_y * 2, 820)
            if viewport:
                width = max(width, viewport[0])
                height = max(height, viewport[1])
        table = self._table_texture(width, height, background)

        x = (width - receipt_layer.width) // 2
        y = (height - receipt_layer.height) // 2 if center_receipt else pad_y
        alpha = receipt_layer.getchannel("A")

        shadow = Image.new("RGBA", receipt_layer.size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda p: int(p * 0.30)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(24))
        self._alpha_composite_clipped(table, shadow, (x + 24, y + 30))

        self._alpha_composite_clipped(table, receipt_layer, (x, y))
        return self._vignette(table)

    def _bend_receipt_layer(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        max_shift = max(2, int(width * 0.018))
        canvas = Image.new("RGBA", (width + max_shift * 2, height), (0, 0, 0, 0))
        for y in range(height):
            t = y / max(1, height - 1)
            shift = (
                math.sin(t * math.pi * 2.1) * max_shift
                + math.sin(t * math.pi * 5.2 + 0.7) * (max_shift * 0.35)
                + (t - 0.5) * max_shift * 0.35
            )
            row = image.crop((0, y, width, y + 1))
            canvas.alpha_composite(row, (max_shift + int(round(shift)), y))
        return canvas

    def _alpha_composite_clipped(self, dest: Image.Image, src: Image.Image, xy: tuple[int, int]) -> None:
        x, y = xy
        src_left = max(0, -x)
        src_top = max(0, -y)
        dest_x = max(0, x)
        dest_y = max(0, y)
        visible_w = min(src.width - src_left, dest.width - dest_x)
        visible_h = min(src.height - src_top, dest.height - dest_y)
        if visible_w <= 0 or visible_h <= 0:
            return
        cropped = src.crop((src_left, src_top, src_left + visible_w, src_top + visible_h))
        dest.alpha_composite(cropped, (dest_x, dest_y))

    def _paper_texture(self, width: int, height: int, rng: random.Random) -> Image.Image:
        paper_asset = self.assets.get("paper")
        if isinstance(paper_asset, Image.Image):
            base = self._fit_cover(paper_asset, width, height)
            base = ImageEnhance.Color(base).enhance(0.10)
            base = ImageEnhance.Brightness(base).enhance(1.08)
            base = ImageEnhance.Contrast(base).enhance(0.92)
        else:
            base = Image.new("RGBA", (width, height), (248, 247, 243, 255))

        noise = Image.effect_noise((width, height), 5).convert("L")
        noise_rgba = Image.merge("RGBA", (noise, noise, noise, Image.new("L", (width, height), 10)))
        base = Image.alpha_composite(base.convert("RGBA"), noise_rgba)
        draw = ImageDraw.Draw(base, "RGBA")

        for _ in range(7):
            x1 = rng.randint(-30, width - 50)
            y1 = rng.randint(0, height)
            x2 = x1 + rng.randint(110, 340)
            y2 = y1 + rng.randint(-90, 90)
            draw.line((x1, y1, x2, y2), fill=(96, 96, 90, rng.randint(7, 15)), width=rng.randint(1, 2))
            draw.line((x1 + 3, y1 + 2, x2 + 3, y2 + 2), fill=(255, 255, 255, rng.randint(10, 18)), width=1)

        grime_asset = self.assets.get("grime")
        if isinstance(grime_asset, Image.Image):
            grime = self._fit_cover(grime_asset, width, height)
            alpha = grime.getchannel("A").point(lambda p: min(42, int(p * 0.18)))
            grime = ImageOps.grayscale(grime).convert("RGBA")
            grime.putalpha(alpha)
            base.alpha_composite(grime)

        mask = self._torn_paper_mask(width, height, rng)
        base.putalpha(mask)
        return base

    def _table_texture(self, width: int, height: int, style: str) -> Image.Image:
        style_key = style.lower()
        wood_asset = self.assets.get("wood")
        if isinstance(wood_asset, Image.Image) and ("wood" in style_key or "table" in style_key):
            image = self._fit_cover(wood_asset, width, height)
            if "dark" in style_key:
                image = ImageEnhance.Brightness(image).enhance(0.62)
                image = ImageEnhance.Contrast(image).enhance(1.12)
            else:
                image = ImageEnhance.Brightness(image).enhance(1.02)
                image = ImageEnhance.Contrast(image).enhance(1.04)
            return self._scene_light(image)

        if "dark" in style_key:
            low = (45, 35, 29)
            high = (112, 84, 62)
        elif "counter" in style_key:
            low = (128, 128, 122)
            high = (219, 216, 205)
        elif "plain" in style_key:
            low = (219, 221, 224)
            high = (248, 249, 250)
        else:
            low = (122, 88, 56)
            high = (214, 170, 112)

        noise = Image.effect_noise((width, height), 44 if "counter" in style_key else 32).convert("L")
        noise = noise.filter(ImageFilter.GaussianBlur(1.1))
        image = ImageOps.colorize(noise, black=low, white=high).convert("RGBA")
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        rng = random.Random(stable_seed(style + str(width) + str(height)))

        if "counter" in style_key:
            for _ in range(max(80, (width * height) // 90000)):
                x1 = rng.randint(-100, width)
                y1 = rng.randint(0, height)
                x2 = x1 + rng.randint(160, 520)
                y2 = y1 + rng.randint(-80, 80)
                draw.line((x1, y1, x2, y2), fill=(246, 246, 238, rng.randint(12, 28)), width=rng.choice([1, 1, 2]))
        elif "plain" in style_key:
            for _ in range(max(70, (width * height) // 120000)):
                x = rng.randint(0, width)
                y = rng.randint(0, height)
                r = rng.randint(1, 3)
                draw.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, rng.randint(12, 30)))
        else:
            for y in range(-40, height + 40, 16):
                wobble = rng.randint(-6, 6)
                color = tuple(max(0, min(255, c + rng.randint(-18, 18))) for c in high)
                draw.line((0, y + wobble, width, y + rng.randint(-7, 7)), fill=color + (18,), width=rng.choice([1, 1, 2]))
            for _ in range(max(120, height // 8)):
                y = rng.randint(0, height)
                x = rng.randint(0, width)
                length = rng.randint(100, 520)
                color = tuple(max(0, min(255, c + rng.randint(-26, 26))) for c in high)
                draw.line((x, y, min(width, x + length), y + rng.randint(-5, 5)), fill=color + (16,), width=rng.choice([1, 1, 2]))

        for _ in range(max(70, height // 12)):
            y = rng.randint(0, height)
            x = rng.randint(0, width)
            length = rng.randint(60, 260)
            color = tuple(max(0, min(255, c + rng.randint(-18, 18))) for c in low)
            draw.line((x, y, min(width, x + length), y + rng.randint(-3, 3)), fill=color + (9,), width=1)
        image.alpha_composite(overlay)
        return self._scene_light(image)

    def _fit_cover(self, image: Image.Image, width: int, height: int) -> Image.Image:
        source = image.convert("RGBA")
        scale = max(width / source.width, height / source.height)
        resized = source.resize(
            (max(1, int(source.width * scale)), max(1, int(source.height * scale))),
            Image.Resampling.LANCZOS,
        )
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        return resized.crop((left, top, left + width, top + height))

    def _fit_contain(self, image: Image.Image, max_width: int, max_height: int) -> Image.Image:
        source = self._trim_alpha(image.convert("RGBA"))
        scale = min(max_width / source.width, max_height / source.height, 1.0)
        return source.resize(
            (max(1, int(source.width * scale)), max(1, int(source.height * scale))),
            Image.Resampling.LANCZOS,
        )

    def _tile_vertical(self, image: Image.Image, width: int, height: int) -> Image.Image:
        source = image.convert("RGBA")
        scale = width / source.width
        tile = source.resize((width, max(1, int(source.height * scale))), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        y = 0
        index = 0
        while y < height:
            piece = tile
            if index % 2:
                piece = ImageOps.mirror(piece)
            canvas.alpha_composite(piece, (0, y))
            y += piece.height
            index += 1
        return canvas

    def _trim_alpha(self, image: Image.Image) -> Image.Image:
        bbox = image.getbbox()
        if not bbox:
            return image
        return image.crop(bbox)

    def _scene_light(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        result = image.convert("RGBA")
        small_w, small_h = 240, 320
        highlight = Image.new("L", (small_w, small_h), 0)
        px = highlight.load()
        for yy in range(small_h):
            for xx in range(small_w):
                dx = (xx - small_w * 0.34) / (small_w * 0.58)
                dy = (yy - small_h * 0.23) / (small_h * 0.70)
                distance = math.sqrt(dx * dx + dy * dy)
                px[xx, yy] = int(max(0.0, 1.0 - distance) ** 1.7 * 64)
        highlight = highlight.resize((width, height), Image.Resampling.BICUBIC)
        warm = Image.new("RGBA", (width, height), (255, 235, 205, 0))
        warm.putalpha(highlight)
        result.alpha_composite(warm)

        shade = Image.new("L", (small_w, small_h), 0)
        spx = shade.load()
        for yy in range(small_h):
            for xx in range(small_w):
                right = xx / (small_w - 1)
                bottom = yy / (small_h - 1)
                spx[xx, yy] = int(max(0.0, right * 0.55 + bottom * 0.45 - 0.35) ** 1.4 * 80)
        shade = shade.resize((width, height), Image.Resampling.BICUBIC)
        dark = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        dark.putalpha(shade)
        result.alpha_composite(dark)
        return result

    def _torn_paper_mask(self, width: int, height: int, rng: random.Random) -> Image.Image:
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        points: list[tuple[int, int]] = []
        for x in range(0, width + 1, 28):
            points.append((x, rng.randint(0, 3)))
        for y in range(28, height + 1, 38):
            points.append((width - rng.randint(0, 3), y))
        for x in range(width, -1, -28):
            points.append((x, height - rng.randint(0, 3)))
        for y in range(height, -1, -38):
            points.append((rng.randint(0, 3), y))
        draw.polygon(points, fill=255)
        return mask.filter(ImageFilter.GaussianBlur(0.35))

    def _vignette(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        small_w, small_h = 240, 320
        mask = Image.new("L", (small_w, small_h), 0)
        px = mask.load()
        cx = (small_w - 1) / 2
        cy = (small_h - 1) / 2
        for yy in range(small_h):
            for xx in range(small_w):
                dx = (xx - cx) / cx
                dy = (yy - cy) / cy
                distance = math.sqrt(dx * dx + dy * dy)
                alpha = int(max(0.0, min(1.0, (distance - 0.55) / 0.55)) ** 1.8 * 62)
                px[xx, yy] = alpha
        mask = mask.resize((width, height), Image.Resampling.BICUBIC)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay.putalpha(mask)
        result = image.copy()
        result.alpha_composite(overlay)
        return result

    def _notice_bar(self, draw: ImageDraw.ImageDraw, left: int, right: int, y: int) -> int:
        lines = [SAFE_NOTICE]
        line_boxes = [draw.textbbox((0, 0), line, font=self.font_notice) for line in lines]
        line_height = max(box[3] - box[1] for box in line_boxes)
        h = line_height * len(lines) + 20
        draw.rounded_rectangle((left, y, right, y + h), radius=7, outline=(30, 30, 30, 180), width=2)
        text_y = y + 8
        for line, bbox in zip(lines, line_boxes):
            line_width = bbox[2] - bbox[0]
            draw.text(((left + right - line_width) // 2, text_y), line, font=self.font_notice, fill=(18, 18, 18))
            text_y += line_height
        return y + h + 28

    def _draw_logo(self, canvas: Image.Image, draw: ImageDraw.ImageDraw, store_key: str, title: str, y: int, width: int) -> int:
        logos = self.assets.get("logos")
        if isinstance(logos, dict) and isinstance(logos.get(store_key), Image.Image):
            max_sizes = {
                "target": (260, 130),
                "walmart": (380, 118),
                "cvs": (380, 112),
                "costco": (390, 96),
            }
            max_width, max_height = max_sizes.get(store_key, (360, 120))
            logo = self._fit_contain(logos[store_key], max_width, max_height)
            x = (width - logo.width) // 2
            canvas.alpha_composite(logo, (x, y))
            return y + logo.height + 28

        title = title.upper().replace("WAL-MART", "WALMART")
        if store_key == "target":
            cx = width // 2
            draw.ellipse((cx - 46, y, cx + 46, y + 92), outline=(0, 0, 0), width=10)
            draw.ellipse((cx - 17, y + 29, cx + 17, y + 63), fill=(0, 0, 0))
            y += 106
            y = self._center(draw, title, y, self.font_bold, fill=(0, 0, 0), max_width=width - 70)
        elif store_key == "walmart":
            y = self._draw_walmart_header(draw, title, y, width)
        elif store_key == "cvs":
            y = self._draw_cvs_header(draw, title, y, width)
        else:
            y = self._draw_costco_header(draw, title, y, width)
        return y + 24

    def _draw_walmart_header(self, draw: ImageDraw.ImageDraw, title: str, y: int, width: int) -> int:
        text = title.title()
        bbox = draw.textbbox((0, 0), text, font=self.font_title)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2 - 26
        draw.text((x, y), text, font=self.font_title, fill=(0, 0, 0))
        spark_cx = x + text_w + 42
        spark_cy = y + 32
        for angle in range(0, 360, 60):
            radians = math.radians(angle)
            x1 = spark_cx + math.cos(radians) * 8
            y1 = spark_cy + math.sin(radians) * 8
            x2 = spark_cx + math.cos(radians) * 22
            y2 = spark_cy + math.sin(radians) * 22
            draw.line((x1, y1, x2, y2), fill=(0, 0, 0), width=7)
        return y + 62

    def _draw_cvs_header(self, draw: ImageDraw.ImageDraw, title: str, y: int, width: int) -> int:
        text = title.upper()
        bbox = draw.textbbox((0, 0), text, font=self.font_title)
        text_w = bbox[2] - bbox[0]
        heart_w = 48
        x = (width - text_w - heart_w - 14) // 2
        draw.text((x + heart_w + 14, y), text, font=self.font_title, fill=(0, 0, 0))
        hx = x
        hy = y + 10
        draw.ellipse((hx, hy, hx + 26, hy + 26), fill=(0, 0, 0))
        draw.ellipse((hx + 20, hy, hx + 46, hy + 26), fill=(0, 0, 0))
        draw.polygon([(hx + 1, hy + 17), (hx + 45, hy + 17), (hx + 23, hy + 48)], fill=(0, 0, 0))
        return y + 62

    def _draw_costco_header(self, draw: ImageDraw.ImageDraw, title: str, y: int, width: int) -> int:
        main = title.upper().replace(" WHOLESALE", "")
        bbox = draw.textbbox((0, 0), main, font=self.font_title)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        draw.text((x, y), main, font=self.font_title, fill=(0, 0, 0))
        y += 54
        line_left = max(70, x - 4)
        line_right = min(width - 70, x + text_w + 4)
        draw.line((line_left, y, line_right, y), fill=(0, 0, 0), width=4)
        draw.line((line_left + 18, y + 9, line_right - 18, y + 9), fill=(0, 0, 0), width=3)
        y += 15
        return self._center(draw, "WHOLESALE", y, self.font_bold, fill=(0, 0, 0), max_width=width - 70)

    def _draw_item(self, draw: ImageDraw.ImageDraw, item: ReceiptItem, left: int, right: int, y: int) -> int:
        if item.quantity != Decimal("1"):
            qty_line = f"{fmt_qty(item.quantity)} @ {fmt_money(item.unit_price)} ea"
            draw.text((left, y), qty_line, font=self.font_small, fill=(42, 42, 42))
            y += 26

        prefix = (item.upc or "SKU").strip()
        description = item.description.strip() or "ITEM"
        text = f"{prefix} {description}"
        max_text_width = (right - left) - 126
        while draw.textlength(text, font=self.font_regular) > max_text_width and len(description) > 8:
            description = description[:-1]
            text = f"{prefix} {description}..."
        self._lr(draw, text.upper(), fmt_money(item.total), left, right, y, self.font_regular)
        y += 35
        flags = []
        if item.category:
            flags.append(item.category.upper())
        flags.append("TAX" if item.taxable else "NO TAX")
        draw.text((left + 22, y), "  ".join(flags), font=self.font_tiny, fill=(80, 80, 80))
        return y + 28

    def _lr(
        self,
        draw: ImageDraw.ImageDraw,
        left_text: str,
        right_text: str,
        left: int,
        right: int,
        y: int,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int] = (0, 0, 0),
    ) -> None:
        draw.text((left, y), left_text, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), right_text, font=font)
        draw.text((right - (bbox[2] - bbox[0]), y), right_text, font=font, fill=fill)

    def _center(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        y: int,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int] = (0, 0, 0),
        max_width: int | None = None,
    ) -> int:
        lines = self._wrap(draw, text, font, max_width or 540)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(((620 - (bbox[2] - bbox[0])) // 2, y), line, font=font, fill=fill)
            y += (bbox[3] - bbox[1]) + 9
        return y

    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
        words = str(text).split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _rule(self, draw: ImageDraw.ImageDraw, left: int, right: int, y: int) -> int:
        draw.line((left, y, right, y), fill=(32, 32, 32), width=2)
        return y + 6

    def _fake_barcode(self, draw: ImageDraw.ImageDraw, left: int, right: int, y: int, height: int, seed: str) -> int:
        rng = random.Random(stable_seed(seed))
        x = left
        while x < right:
            bar_w = rng.choice([2, 3, 4, 6])
            gap = rng.choice([2, 3, 5])
            if rng.random() > 0.18:
                draw.rectangle((x, y, min(x + bar_w, right), y + height), fill=(0, 0, 0))
            x += bar_w + gap
        return y + height + 18

    def _fake_qr(self, draw: ImageDraw.ImageDraw, x: int, y: int, size: int, seed: str) -> int:
        rng = random.Random(stable_seed(seed + "qr"))
        cells = 21
        cell = size // cells
        draw.rectangle((x - 8, y - 8, x + cells * cell + 8, y + cells * cell + 8), fill=(250, 250, 250))
        for cy in range(cells):
            for cx in range(cells):
                finder = (
                    (cx < 7 and cy < 7)
                    or (cx >= cells - 7 and cy < 7)
                    or (cx < 7 and cy >= cells - 7)
                )
                value = finder or rng.random() > 0.57
                if value:
                    draw.rectangle((x + cx * cell, y + cy * cell, x + (cx + 1) * cell - 1, y + (cy + 1) * cell - 1), fill=(0, 0, 0))
        return y + size + 20

    def _transaction_id(self, seed: str) -> str:
        return hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:10].upper()

    def _auth_code(self, seed: str) -> str:
        return str(stable_seed(seed + "auth"))[-6:].rjust(6, "0")


class ReceiptStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(1050, 690)

        self.renderer = ReceiptRenderer()
        self.items: list[ReceiptItem] = []
        self.draw_strokes: list[dict[str, Any]] = []
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.current_receipt: Image.Image | None = None
        self.current_scene: Image.Image | None = None
        self.refresh_job: str | None = None

        self.vars: dict[str, tk.StringVar] = {}
        self.store_var = tk.StringVar(value="target")
        self.background_var = tk.StringVar(value="Light wood table")
        self.scene_scale_var = tk.DoubleVar(value=100.0)
        self.scene_scale_label_var = tk.StringVar(value="100%")
        self.draw_color_var = tk.StringVar(value="Black")
        self.draw_size_var = tk.DoubleVar(value=5.0)
        self.taxable_var = tk.BooleanVar(value=True)

        self._build_style()
        self._build_ui()
        self._load_template_defaults("target", preserve_items=False)
        self._load_demo_items()
        self._queue_refresh()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TButton", padding=(10, 6))
        style.configure("TLabel", padding=(0, 2))
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=14)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        title = ttk.Label(left, text=APP_TITLE, style="Header.TLabel")
        title.grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(left, text="Creates visibly marked prop receipt mockups.")
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 10))

        notebook = ttk.Notebook(left)
        notebook.grid(row=2, column=0, sticky="nsew")
        left.rowconfigure(2, weight=1)

        self._build_receipt_tab(notebook)
        self._build_items_tab(notebook)
        self._build_import_tab(notebook)
        self._build_export_tab(notebook)

        right = ttk.Frame(self, padding=(0, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(right)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_preview).pack(side="left")
        ttk.Button(toolbar, text="Save PNG", command=self._save_png).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Save 4K Scene", command=self._save_4k_scene).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Fullscreen", command=self._fullscreen_preview).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Draw", command=self._open_draw_editor).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Clear Ink", command=self._clear_draw_strokes).pack(side="left", padx=(8, 0))
        ttk.Label(toolbar, text="Background").pack(side="left", padx=(18, 6))
        background = ttk.Combobox(
            toolbar,
            textvariable=self.background_var,
            values=["Light wood table", "Dark wood table", "Stone counter", "Plain studio"],
            state="readonly",
            width=18,
        )
        background.pack(side="left")
        background.bind("<<ComboboxSelected>>", lambda _event: self._queue_refresh())
        ttk.Label(toolbar, text="Receipt size").pack(side="left", padx=(18, 6))
        scale_control = ttk.Scale(
            toolbar,
            from_=60,
            to=140,
            variable=self.scene_scale_var,
            command=self._on_scene_scale_changed,
            length=130,
        )
        scale_control.pack(side="left")
        ttk.Label(toolbar, textvariable=self.scene_scale_label_var, width=5).pack(side="left", padx=(6, 0))

        preview_frame = ttk.Frame(right)
        preview_frame.grid(row=1, column=0, sticky="nsew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(preview_frame, bg="#d7d7d7", highlightthickness=0)
        vscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_canvas.yview)
        hscroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview_canvas.xview)
        self.preview_canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.preview_canvas.bind("<Configure>", lambda _event: self._queue_refresh(350))

    def _build_receipt_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Receipt")
        frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(frame, text="Store style").grid(row=row, column=0, sticky="w")
        store_combo = ttk.Combobox(
            frame,
            textvariable=self.store_var,
            values=STORE_ORDER,
            state="readonly",
            width=24,
        )
        store_combo.grid(row=row, column=1, sticky="ew", pady=3)
        store_combo.bind("<<ComboboxSelected>>", self._on_store_changed)
        row += 1

        for key, label in [
            ("display_name", "Display name"),
            ("location", "Location"),
            ("phone", "Phone"),
            ("store_no", "Store #"),
            ("register", "Register"),
            ("cashier", "Cashier"),
            ("date", "Date"),
            ("time", "Time"),
            ("tax_rate_percent", "Tax rate %"),
            ("payment_method", "Payment"),
            ("card_last4", "Card last 4"),
            ("transaction_id", "Transaction ID"),
        ]:
            self.vars[key] = tk.StringVar()
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(frame, textvariable=self.vars[key], width=28)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.vars[key].trace_add("write", lambda *_args: self._queue_refresh())
            row += 1

        ttk.Button(frame, text="Reset fields for selected style", command=lambda: self._load_template_defaults(self.store_var.get(), preserve_items=True)).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_items_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Items")
        frame.columnconfigure(1, weight=1)
        row = 0

        self.item_vars = {
            "upc": tk.StringVar(),
            "description": tk.StringVar(),
            "quantity": tk.StringVar(value="1"),
            "unit_price": tk.StringVar(value="0.00"),
            "category": tk.StringVar(),
        }
        for key, label in [
            ("upc", "UPC/SKU"),
            ("description", "Description"),
            ("quantity", "Qty"),
            ("unit_price", "Unit price"),
            ("category", "Category"),
        ]:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(frame, textvariable=self.item_vars[key]).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1
        ttk.Checkbutton(frame, text="Taxable", variable=self.taxable_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
        row += 1
        button_row = ttk.Frame(frame)
        button_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(7, 8))
        ttk.Button(button_row, text="Add item", command=self._add_item).pack(side="left")
        ttk.Button(button_row, text="Update selected", command=self._update_selected_item).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Remove", command=self._remove_selected_item).pack(side="left", padx=(8, 0))
        row += 1

        columns = ("qty", "desc", "price", "tax")
        self.items_tree = ttk.Treeview(frame, columns=columns, show="headings", height=11)
        self.items_tree.heading("qty", text="Qty")
        self.items_tree.heading("desc", text="Description")
        self.items_tree.heading("price", text="Total")
        self.items_tree.heading("tax", text="Tax")
        self.items_tree.column("qty", width=48, anchor="center")
        self.items_tree.column("desc", width=185)
        self.items_tree.column("price", width=74, anchor="e")
        self.items_tree.column("tax", width=48, anchor="center")
        self.items_tree.grid(row=row, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        self.items_tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_item_into_form())
        row += 1

        totals = ttk.Frame(frame)
        totals.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.totals_label = ttk.Label(totals, text="")
        self.totals_label.pack(side="left")
        ttk.Button(totals, text="Clear all", command=self._clear_items).pack(side="right")

    def _build_import_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="AI Import")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="Prompt to copy into AI").grid(row=0, column=0, sticky="w")
        self.prompt_text = tk.Text(frame, height=10, wrap="word", font=("Consolas", 9))
        self.prompt_text.grid(row=1, column=0, sticky="nsew", pady=(3, 8))
        self.prompt_text.insert("1.0", AI_IMPORT_PROMPT)
        self.prompt_text.configure(state="disabled")

        prompt_buttons = ttk.Frame(frame)
        prompt_buttons.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(prompt_buttons, text="Copy prompt", command=self._copy_prompt).pack(side="left")
        ttk.Button(prompt_buttons, text="Load example JSON", command=self._load_example_json).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Paste JSON here").grid(row=3, column=0, sticky="w")
        self.json_text = tk.Text(frame, height=11, wrap="word", font=("Consolas", 9))
        self.json_text.grid(row=4, column=0, sticky="nsew", pady=(3, 8))
        ttk.Button(frame, text="Import JSON into fields", command=self._import_json).grid(row=5, column=0, sticky="ew")

    def _build_export_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Export")
        frame.columnconfigure(0, weight=1)
        text = (
            "Exports are PNG images with a single visible PROP / NOT VALID label. "
            "The paper height grows with the number of items. Receipt size controls "
            "the preview, fullscreen, and 4K textured background scene."
        )
        ttk.Label(frame, text=text, wraplength=310).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(frame, text="Save receipt PNG", command=self._save_png).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(frame, text="Save 4K scene PNG", command=self._save_4k_scene).grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Button(frame, text="Open fullscreen preview", command=self._fullscreen_preview).grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Button(frame, text="Copy current data JSON", command=self._copy_current_json).grid(row=4, column=0, sticky="ew", pady=4)

    def _on_store_changed(self, _event: Any = None) -> None:
        self._load_template_defaults(self.store_var.get(), preserve_items=True)

    def _load_template_defaults(self, store_key: str, preserve_items: bool) -> None:
        template = STORE_TEMPLATES.get(store_key, STORE_TEMPLATES["target"])
        values = {
            "display_name": template["display_name"],
            "location": template["location"],
            "phone": template["phone"],
            "store_no": template["store_no"],
            "register": template["register"],
            "cashier": template["cashier"],
            "date": now_date(),
            "time": now_time(),
            "tax_rate_percent": template["tax_rate"],
            "payment_method": template["payment"],
            "card_last4": template["card_last4"],
            "transaction_id": "",
        }
        for key, value in values.items():
            if key in self.vars:
                self.vars[key].set(str(value))
        if not preserve_items:
            self.items.clear()
        self._refresh_items_tree()
        self._queue_refresh()

    def _load_demo_items(self) -> None:
        self.items = [
            ReceiptItem("270030028", "Morning meat alt", Decimal("1"), Decimal("3.79"), True, "grocery"),
            ReceiptItem("211180116", "Vegetable bites", Decimal("1"), Decimal("4.79"), True, "grocery"),
            ReceiptItem("284060377", "Oatmilk", Decimal("2"), Decimal("3.49"), True, "grocery"),
            ReceiptItem("284000087", "Biscuit dough", Decimal("1"), Decimal("1.89"), True, "grocery"),
        ]
        self._refresh_items_tree()

    def _form_data(self) -> dict[str, Any]:
        return {
            "store": self.store_var.get(),
            "background": self.background_var.get(),
            "scene_scale_percent": round(float(self.scene_scale_var.get()), 1),
            **{key: var.get().strip() for key, var in self.vars.items()},
        }

    def _add_item(self) -> None:
        item = self._item_from_form()
        if item is None:
            return
        self.items.append(item)
        self._clear_item_form()
        self._refresh_items_tree()
        self._queue_refresh()

    def _update_selected_item(self) -> None:
        selection = self.items_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Select an item first.")
            return
        item = self._item_from_form()
        if item is None:
            return
        index = int(selection[0])
        if 0 <= index < len(self.items):
            self.items[index] = item
            self._refresh_items_tree()
            self.items_tree.selection_set(str(index))
            self._queue_refresh()

    def _remove_selected_item(self) -> None:
        selection = self.items_tree.selection()
        if not selection:
            return
        indexes = sorted((int(item_id) for item_id in selection), reverse=True)
        for index in indexes:
            if 0 <= index < len(self.items):
                del self.items[index]
        self._refresh_items_tree()
        self._queue_refresh()

    def _clear_items(self) -> None:
        if self.items and not messagebox.askyesno(APP_TITLE, "Clear all items?"):
            return
        self.items.clear()
        self._refresh_items_tree()
        self._queue_refresh()

    def _item_from_form(self) -> ReceiptItem | None:
        description = self.item_vars["description"].get().strip()
        if not description:
            messagebox.showerror(APP_TITLE, "Item description is required.")
            return None
        quantity = decimal_from_text(self.item_vars["quantity"].get(), "1")
        price = money(decimal_from_text(self.item_vars["unit_price"].get(), "0"))
        if quantity <= 0:
            messagebox.showerror(APP_TITLE, "Quantity must be greater than zero.")
            return None
        if price < 0:
            messagebox.showerror(APP_TITLE, "Price cannot be negative.")
            return None
        return ReceiptItem(
            upc=self.item_vars["upc"].get().strip(),
            description=description,
            quantity=quantity,
            unit_price=price,
            taxable=bool(self.taxable_var.get()),
            category=self.item_vars["category"].get().strip(),
        )

    def _clear_item_form(self) -> None:
        self.item_vars["upc"].set("")
        self.item_vars["description"].set("")
        self.item_vars["quantity"].set("1")
        self.item_vars["unit_price"].set("0.00")
        self.item_vars["category"].set("")
        self.taxable_var.set(True)

    def _load_selected_item_into_form(self) -> None:
        selection = self.items_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if not (0 <= index < len(self.items)):
            return
        item = self.items[index]
        self.item_vars["upc"].set(item.upc)
        self.item_vars["description"].set(item.description)
        self.item_vars["quantity"].set(fmt_qty(item.quantity))
        self.item_vars["unit_price"].set(str(item.unit_price))
        self.item_vars["category"].set(item.category)
        self.taxable_var.set(item.taxable)

    def _refresh_items_tree(self) -> None:
        self.items_tree.delete(*self.items_tree.get_children())
        for index, item in enumerate(self.items):
            self.items_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(fmt_qty(item.quantity), item.description, fmt_money(item.total), "Y" if item.taxable else "N"),
            )
        subtotal = sum((item.total for item in self.items), Decimal("0.00"))
        taxable_subtotal = sum((item.total for item in self.items if item.taxable), Decimal("0.00"))
        tax_rate = decimal_from_text(self.vars.get("tax_rate_percent", tk.StringVar(value="0")).get())
        tax = money(taxable_subtotal * (tax_rate / Decimal("100")))
        total = money(subtotal + tax)
        self.totals_label.configure(text=f"Subtotal {fmt_money(subtotal)}   Tax {fmt_money(tax)}   Total {fmt_money(total)}")

    def _queue_refresh(self, delay: int = 180) -> None:
        if self.refresh_job is not None:
            self.after_cancel(self.refresh_job)
        self.refresh_job = self.after(delay, self._refresh_preview)

    def _on_scene_scale_changed(self, value: str) -> None:
        try:
            scale = float(value)
        except ValueError:
            scale = 100.0
        self.scene_scale_label_var.set(f"{int(round(scale))}%")
        self._queue_refresh(60)

    def _scene_scale_multiplier(self) -> float:
        try:
            scale = float(self.scene_scale_var.get()) / 100.0
        except (tk.TclError, ValueError):
            scale = 1.0
        return max(0.60, min(1.40, scale))

    def _scaled_receipt_for_scene(self, receipt: Image.Image, width: int, height: int) -> Image.Image:
        base_scale = min((width * 0.68) / receipt.width, (height * 0.70) / receipt.height, 2.65)
        scale = max(0.10, base_scale * self._scene_scale_multiplier())
        return receipt.resize(
            (max(1, int(receipt.width * scale)), max(1, int(receipt.height * scale))),
            Image.Resampling.LANCZOS,
        )

    def _draw_rgba(self, color_name: str) -> tuple[int, int, int, int]:
        colors = {
            "Black": (10, 10, 10, 230),
            "Red": (190, 28, 28, 220),
            "Blue": (24, 74, 180, 220),
            "Highlighter": (255, 224, 60, 118),
        }
        return colors.get(color_name, colors["Black"])

    def _apply_draw_strokes(self, receipt: Image.Image) -> Image.Image:
        if not self.draw_strokes:
            return receipt
        result = receipt.convert("RGBA")
        overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        for stroke in self.draw_strokes:
            points = stroke.get("points") or []
            if len(points) < 2:
                continue
            color = tuple(stroke.get("rgba") or self._draw_rgba("Black"))
            width = max(1, int(stroke.get("width", 5)))
            draw.line([tuple(point) for point in points], fill=color, width=width, joint="curve")
            radius = max(1, width // 2)
            for x, y in points:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        result.alpha_composite(overlay)
        return result

    def _clear_draw_strokes(self) -> None:
        if self.draw_strokes and not messagebox.askyesno(APP_TITLE, "Clear all drawing on the receipt?"):
            return
        self.draw_strokes.clear()
        self._queue_refresh(20)

    def _open_draw_editor(self) -> None:
        base_receipt = self.renderer.render_receipt(self._form_data(), self.items)
        receipt = self._apply_draw_strokes(base_receipt)

        top = tk.Toplevel(self)
        top.title("Draw on Receipt")
        top.geometry("760x820")
        top.minsize(520, 520)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(top, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(toolbar, text="Color").pack(side="left")
        color_combo = ttk.Combobox(
            toolbar,
            textvariable=self.draw_color_var,
            values=["Black", "Red", "Blue", "Highlighter"],
            state="readonly",
            width=12,
        )
        color_combo.pack(side="left", padx=(6, 12))
        ttk.Label(toolbar, text="Brush").pack(side="left")
        ttk.Scale(toolbar, from_=2, to=28, variable=self.draw_size_var, length=110).pack(side="left", padx=(6, 12))
        ttk.Button(toolbar, text="Undo", command=lambda: undo()).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Clear", command=lambda: clear()).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Done", command=lambda: done()).pack(side="right")

        canvas = tk.Canvas(top, bg="#2f2f2f", highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")

        state: dict[str, Any] = {"photo": None, "scale": 1.0, "offset": (0, 0), "points": [], "canvas_line": None}

        def canvas_to_receipt(event: tk.Event) -> tuple[int, int]:
            ox, oy = state["offset"]
            scale = state["scale"]
            x = int((event.x - ox) / scale)
            y = int((event.y - oy) / scale)
            return max(0, min(receipt.width - 1, x)), max(0, min(receipt.height - 1, y))

        def redraw() -> None:
            canvas.delete("all")
            cw = max(canvas.winfo_width(), 300)
            ch = max(canvas.winfo_height(), 300)
            scale = min((cw - 30) / receipt.width, (ch - 30) / receipt.height, 1.6)
            scale = max(0.15, scale)
            display = self._apply_draw_strokes(base_receipt)
            display = display.resize((max(1, int(display.width * scale)), max(1, int(display.height * scale))), Image.Resampling.LANCZOS)
            state["photo"] = ImageTk.PhotoImage(display)
            state["scale"] = scale
            state["offset"] = ((cw - display.width) // 2, (ch - display.height) // 2)
            canvas.create_image(*state["offset"], image=state["photo"], anchor="nw")

        def start(event: tk.Event) -> None:
            point = canvas_to_receipt(event)
            state["points"] = [point]

        def drag(event: tk.Event) -> None:
            point = canvas_to_receipt(event)
            points = state["points"]
            if not points:
                points.append(point)
            elif point != points[-1]:
                points.append(point)
            redraw()
            if len(points) >= 2:
                ox, oy = state["offset"]
                scale = state["scale"]
                coords: list[float] = []
                for x, y in points:
                    coords.extend([ox + x * scale, oy + y * scale])
                canvas.create_line(
                    *coords,
                    fill=self._tk_draw_color(self.draw_color_var.get()),
                    width=max(1, float(self.draw_size_var.get()) * scale),
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                    smooth=True,
                )

        def finish(_event: tk.Event) -> None:
            points = state["points"]
            if len(points) >= 2:
                self.draw_strokes.append(
                    {
                        "points": points[:],
                        "rgba": self._draw_rgba(self.draw_color_var.get()),
                        "width": int(round(float(self.draw_size_var.get()))),
                    }
                )
            state["points"] = []
            redraw()
            self._queue_refresh(20)

        def undo() -> None:
            if self.draw_strokes:
                self.draw_strokes.pop()
                redraw()
                self._queue_refresh(20)

        def clear() -> None:
            self.draw_strokes.clear()
            redraw()
            self._queue_refresh(20)

        def done() -> None:
            self._queue_refresh(20)
            top.destroy()

        canvas.bind("<Configure>", lambda _event: redraw())
        canvas.bind("<ButtonPress-1>", start)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", finish)
        top.protocol("WM_DELETE_WINDOW", done)
        top.after(80, redraw)

    def _tk_draw_color(self, color_name: str) -> str:
        colors = {
            "Black": "#111111",
            "Red": "#be1c1c",
            "Blue": "#184ab4",
            "Highlighter": "#ffe03c",
        }
        return colors.get(color_name, "#111111")

    def _refresh_preview(self) -> None:
        self.refresh_job = None
        self._refresh_items_tree()
        data = self._form_data()
        self.current_receipt = self._apply_draw_strokes(self.renderer.render_receipt(data, self.items))
        viewport = (max(self.preview_canvas.winfo_width(), 900), max(self.preview_canvas.winfo_height(), 700))
        scaled = self._scaled_receipt_for_scene(self.current_receipt, *viewport)
        self.current_scene = self.renderer.compose_scene(
            scaled,
            self.background_var.get(),
            viewport=viewport,
            center_receipt=True,
            fixed_viewport=True,
        )
        self.preview_photo = ImageTk.PhotoImage(self.current_scene)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor="nw")
        self.preview_canvas.configure(scrollregion=(0, 0, self.current_scene.width, self.current_scene.height))

    def _save_png(self) -> None:
        if self.current_receipt is None:
            self._refresh_preview()
        OUTPUT_DIR.mkdir(exist_ok=True)
        suggested = OUTPUT_DIR / f"prop_receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filename = filedialog.asksaveasfilename(
            title="Save prop receipt PNG",
            defaultextension=".png",
            initialfile=suggested.name,
            initialdir=str(OUTPUT_DIR),
            filetypes=[("PNG image", "*.png")],
        )
        if not filename:
            return
        assert self.current_receipt is not None
        self.current_receipt.save(filename)
        messagebox.showinfo(APP_TITLE, f"Saved:\n{filename}")

    def _render_scene_for_size(self, width: int, height: int) -> Image.Image:
        if self.current_receipt is None:
            self._refresh_preview()
        assert self.current_receipt is not None
        scaled = self._scaled_receipt_for_scene(self.current_receipt, width, height)
        return self.renderer.compose_scene(
            scaled,
            self.background_var.get(),
            viewport=(width, height),
            center_receipt=True,
            fixed_viewport=True,
        )

    def _save_4k_scene(self) -> None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        suggested = OUTPUT_DIR / f"prop_receipt_scene_4k_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filename = filedialog.asksaveasfilename(
            title="Save 4K prop scene PNG",
            defaultextension=".png",
            initialfile=suggested.name,
            initialdir=str(OUTPUT_DIR),
            filetypes=[("PNG image", "*.png")],
        )
        if not filename:
            return
        scene = self._render_scene_for_size(2160, 3840)
        scene.save(filename)
        messagebox.showinfo(APP_TITLE, f"Saved:\n{filename}")

    def _fullscreen_preview(self) -> None:
        if self.current_receipt is None:
            self._refresh_preview()
        assert self.current_receipt is not None
        top = tk.Toplevel(self)
        top.title("Fullscreen Prop Receipt Preview")
        top.attributes("-fullscreen", True)
        top.configure(bg="black")
        canvas = tk.Canvas(top, highlightthickness=0, bg="black")
        canvas.pack(fill="both", expand=True)

        photo_holder: dict[str, ImageTk.PhotoImage] = {}

        def redraw(_event: Any = None) -> None:
            w = max(canvas.winfo_width(), 900)
            h = max(canvas.winfo_height(), 700)
            receipt = self.current_receipt
            assert receipt is not None
            scaled = self._scaled_receipt_for_scene(receipt, w, h)
            scene = self.renderer.compose_scene(
                scaled,
                self.background_var.get(),
                viewport=(w, h),
                center_receipt=True,
                fixed_viewport=True,
            )
            photo_holder["photo"] = ImageTk.PhotoImage(scene)
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo_holder["photo"], anchor="nw")

        top.bind("<Escape>", lambda _event: top.destroy())
        top.bind("<F11>", lambda _event: top.destroy())
        canvas.bind("<Configure>", redraw)
        top.after(80, redraw)

    def _copy_prompt(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(AI_IMPORT_PROMPT)
        messagebox.showinfo(APP_TITLE, "AI prompt copied to clipboard.")

    def _load_example_json(self) -> None:
        example = {
            "store": "walmart",
            "display_name": "Walmart",
            "location": "3451 Truxel Rd, Sacramento, CA",
            "phone": "916-968-2258",
            "date": now_date(),
            "time": now_time(),
            "store_no": "0023",
            "register": "01234",
            "cashier": "ASSOCIATE",
            "transaction_id": "7ZXXZ523GBA",
            "tax_rate_percent": 8.0,
            "payment_method": "DEBIT",
            "card_last4": "8867",
            "items": [
                {
                    "upc": "012345678976",
                    "description": "HP ENVY printer",
                    "quantity": 1,
                    "unit_price": 69.0,
                    "taxable": True,
                    "category": "electronics",
                }
            ],
        }
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", json.dumps(example, indent=2))

    def _import_json(self) -> None:
        raw = self.json_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showinfo(APP_TITLE, "Paste JSON first.")
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid JSON:\n{exc}")
            return
        if "receipt" in payload and isinstance(payload["receipt"], dict):
            payload = payload["receipt"]
        self._apply_payload(payload)
        messagebox.showinfo(APP_TITLE, "Imported JSON into the receipt.")

    def _apply_payload(self, payload: dict[str, Any]) -> None:
        store = str(payload.get("store") or payload.get("store_style") or self.store_var.get()).lower()
        for key in STORE_ORDER:
            if key in store:
                store = key
                break
        if store not in STORE_TEMPLATES:
            store = self.store_var.get()
        self.store_var.set(store)
        self._load_template_defaults(store, preserve_items=True)

        field_aliases = {
            "display_name": ["display_name", "store_name", "merchant"],
            "location": ["location", "address", "store_address"],
            "phone": ["phone", "telephone"],
            "date": ["date", "purchase_date"],
            "time": ["time", "purchase_time"],
            "store_no": ["store_no", "store_number", "store"],
            "register": ["register", "register_no", "reg"],
            "cashier": ["cashier", "employee", "operator"],
            "transaction_id": ["transaction_id", "transaction", "trans_id", "receipt_id"],
            "tax_rate_percent": ["tax_rate_percent", "tax_percent", "tax_rate"],
            "payment_method": ["payment_method", "payment", "tender"],
            "card_last4": ["card_last4", "last4", "card"],
        }
        for field, aliases in field_aliases.items():
            value = None
            for alias in aliases:
                if alias in payload:
                    value = payload[alias]
                    break
            if value is None:
                continue
            if field == "tax_rate_percent":
                rate = decimal_from_text(str(value), "0")
                if Decimal("0") < rate <= Decimal("1"):
                    rate *= Decimal("100")
                value = str(rate.normalize())
            if isinstance(value, dict):
                value = ", ".join(str(v) for v in value.values() if v)
            if field in self.vars:
                self.vars[field].set(str(value))

        parsed_items = payload.get("items") or payload.get("line_items") or []
        if isinstance(parsed_items, list):
            new_items: list[ReceiptItem] = []
            for item in parsed_items:
                if not isinstance(item, dict):
                    continue
                description = str(item.get("description") or item.get("name") or item.get("item") or "").strip()
                if not description:
                    continue
                quantity = decimal_from_text(str(item.get("quantity", item.get("qty", 1))), "1")
                price_value = item.get("unit_price", item.get("price", item.get("amount", "0")))
                price = money(decimal_from_text(str(price_value), "0"))
                if "amount" in item and "unit_price" not in item and quantity != 0:
                    price = money(price / quantity)
                new_items.append(
                    ReceiptItem(
                        upc=str(item.get("upc") or item.get("sku") or item.get("serial") or "").strip(),
                        description=description,
                        quantity=quantity if quantity > 0 else Decimal("1"),
                        unit_price=price,
                        taxable=bool(item.get("taxable", True)),
                        category=str(item.get("category") or "").strip(),
                    )
                )
            if new_items:
                self.items = new_items
        self._refresh_items_tree()
        self._queue_refresh()

    def _copy_current_json(self) -> None:
        data = self._form_data()
        data["items"] = [
            {
                "upc": item.upc,
                "description": item.description,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "taxable": item.taxable,
                "category": item.category,
            }
            for item in self.items
        ]
        self.clipboard_clear()
        self.clipboard_append(json.dumps(data, indent=2))
        messagebox.showinfo(APP_TITLE, "Current receipt JSON copied.")


def render_self_test() -> list[Path]:
    renderer = ReceiptRenderer()
    OUTPUT_DIR.mkdir(exist_ok=True)
    paths: list[Path] = []
    base_items = [
        ReceiptItem("123456789012", "Notebook", Decimal("1"), Decimal("4.99"), True, "school"),
        ReceiptItem("987654321099", "Cold brew coffee", Decimal("2"), Decimal("3.49"), True, "grocery"),
        ReceiptItem("555000111222", "Gift wrap", Decimal("1"), Decimal("2.25"), False, "seasonal"),
    ]
    for store in STORE_ORDER:
        template = STORE_TEMPLATES[store]
        data = {
            "store": store,
            "display_name": template["display_name"],
            "location": template["location"],
            "phone": template["phone"],
            "store_no": template["store_no"],
            "register": template["register"],
            "cashier": template["cashier"],
            "date": now_date(),
            "time": now_time(),
            "tax_rate_percent": template["tax_rate"],
            "payment_method": template["payment"],
            "card_last4": template["card_last4"],
        }
        receipt = renderer.render_receipt(data, base_items)
        path = OUTPUT_DIR / f"{store}_prop_receipt.png"
        receipt.save(path)
        paths.append(path)
        scene = renderer.compose_scene(receipt, "Light wood table")
        scene.save(OUTPUT_DIR / f"{store}_prop_scene.png")
    return paths


def main() -> None:
    if "--self-test" in sys.argv:
        paths = render_self_test()
        for path in paths:
            print(path)
        return
    app = ReceiptStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
