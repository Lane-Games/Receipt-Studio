# Prop Receipt Studio

Desktop app for creating visibly marked prop receipt mockups for film, testing, and layout work.

## Features

- Four template choices: Target-style, Walmart-style, CVS-style, and Costco-style props.
- Item entry with UPC/SKU, description, quantity, price, category, and taxable flag.
- Automatic subtotal, tax, and total calculation.
- JSON import box plus a built-in AI prompt for structured autofill data.
- Asset-backed paper, wood, grime, and logo rendering, receipt-size control, quick draw marks, PNG export, fullscreen preview, and 4K scene export.

Every generated receipt includes a visible `PROP / NOT VALID` label and is not an official proof of purchase.

## Run From Source

```powershell
.\.venv\Scripts\python.exe .\receipt_studio\sample_receipt_studio.py
```

## Build EXE

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --name PropReceiptStudio --add-data ".\receipt_studio\assets;assets" .\receipt_studio\sample_receipt_studio.py
```

The executable is written to `dist\PropReceiptStudio.exe`.
