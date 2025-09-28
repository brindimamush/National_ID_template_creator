# National ID Template Creator

A Python-based Telegram bot that processes PDFs and generates high-quality PNG images. Designed to automate the extraction and conversion of PDF documents into images, making it easier for clients to work with ID templates and other PDF content.

## Features

- Converts PDF pages into PNG images automatically.
- Supports multi-page PDFs.
- High-quality image output using Pillow.
- Easy integration with Telegram via the Bot API.
- Optimized for speed and accuracy.

## Tech Stack

- **Python 3.x**
- [PyMuPDF](https://pypi.org/project/PyMuPDF/) – PDF parsing and extraction.
- [Pillow](https://pillow.readthedocs.io/) – Image processing.
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) – Optional text extraction.
- [python-telegram-bot](https://python-telegram-bot.org/) – Telegram bot integration.

## Installation

1. Clone the repository:

```bash
git clone https://github.com/brindimamush/National_ID_template_creator.git
cd National_ID_template_creator

2. python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

3.pip install -r requirements.txt

4.TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" and ADMINIDS = "YOUR TELEGRAM USER ID"

5.start the bot python bot.py

Project Structure
National_ID_template_creator/
├── bot.py              # Main bot script
├── utils/              # Helper modules for PDF processing and image conversion
├── requirements.txt    # Python dependencies
├── README.md           # Project documentation
└── examples/           # Sample PDFs and generated PNGs