import os
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pytesseract
from rembg import remove
import time

# Utility log function
def log(step, msg):
    print(f"[{step}] {msg}")

# ---- IMAGE PROCESSING ----
def extract_images(pdf_doc, temp_dir=".temp"):
    """Extracts up to 5 images from the first page of a PDF."""
    os.makedirs(temp_dir, exist_ok=True)
    images = []
    try:
        log("Step 1", "Extracting images from PDF...")
        page = pdf_doc[0]
        raw_images = page.get_images(full=True)
        for i, img in enumerate(raw_images[:5], start=1):
            xref = img[0]
            pix = fitz.Pixmap(pdf_doc, xref)
            out_path = os.path.join(temp_dir, f"image_{i}.png")
            # Save pixmap as PNG
            if pix.n - pix.alpha < 4:  # this is GRAY or RGB
                pix.save(out_path)
            else:  # CMYK: convert to RGB first
                pix0 = fitz.Pixmap(fitz.csRGB, pix)
                pix0.save(out_path)
                pix0 = None
            images.append(out_path)
            pix = None
        log("Step 1", f"Extracted {len(images)} images")
    except Exception as e:
        log("Step 1", f"Error extracting images: {e}")
    return images

def process_image1_and_2(pdf_doc, template_path, image3_path, final_size=(1832, 560)):
    """
    Processes images for the final composition.
    - Image 1 is now cropped from image3_path.
    - Image 2 is extracted directly from a PDF rectangle.
    """
    try:
        log("Step 2", "Processing image 1 and 2...")

        page = pdf_doc[0]
        # Rectangle for image 2 from the PDF
        source_rect2 = fitz.Rect(110.0, 411.0, 274.0, 573.0)

        # Destination positions and sizes for pasting
        dest_img1_pos, dest_img1_size = (49, 150), (285, 363)
        dest_img2_pos, dest_img2_size = (1357, 38), (435, 436)

        # Create the base canvas from the template
        final_image = Image.new("RGBA", final_size, (255, 255, 255, 255))
        template = Image.open(template_path).resize(final_size, Image.Resampling.LANCZOS)
        final_image.paste(template, (0, 0))

        # --- MODIFIED: Process Image 1 from image_3.png ---
        log("Step 2", "Cropping image 1 from the extracted image 3...")
        img3 = Image.open(image3_path)
        # Crop coordinates: (x=524, y=411, w=848, h=1093)
        # PIL crop box is (left, upper, right, lower)
        crop_box = (524, 411, 524 + 848, 411 + 1093)
        img1 = img3.crop(crop_box)
        
        # Remove background, resize, and paste image 1
        img1_no_bg = remove(img1)
        resized_img1 = img1_no_bg.resize(dest_img1_size, Image.Resampling.LANCZOS)
        final_image.paste(resized_img1, dest_img1_pos, mask=resized_img1)
        log("Step 2", "Pasted new image 1.")

        # --- UNCHANGED: Process Image 2 from PDF ---
        zoom_factor = 3.0
        matrix = fitz.Matrix(zoom_factor, zoom_factor)
        pix2 = page.get_pixmap(matrix=matrix, clip=source_rect2)
        img2 = Image.frombytes("RGB", [pix2.width, pix2.height], pix2.samples)
        resized_img2 = img2.resize(dest_img2_size, Image.Resampling.LANCZOS)
        final_image.paste(resized_img2, dest_img2_pos)
        log("Step 2", "Pasted image 2.")

        # Small reuse of image1
        new_img1_resized = img1_no_bg.resize((81, 99), Image.Resampling.LANCZOS)
        final_image.paste(new_img1_resized, (716, 416), mask=new_img1_resized)

        log("Step 2", "Done with image 1 & 2")
        return final_image
    except Exception as e:
        log("Step 2", f"Error: {e}")
        return None

def process_image3_image4_with_ocr(template, image3_path, image4_path):
    """Crops regions from images 3 and 4, performs OCR, and pastes them."""
    try:
        log("Step 3", "Processing image 3 and 4 with OCR...")
        regions = [
            {"type": "ocr", "source_img": "img3", "snapshot": (231, 2451, 957, 111), "paste": (355, 385)},
            {"type": "paste", "source_img": "img3", "snapshot": (525, 2628, 825, 285), "paste": (417, 439, 220, 75)},
            {"type": "paste", "source_img": "img3", "snapshot": (1778, 1128, 56, 450), "paste": (16, 337, 20, 115)},
            {"type": "paste", "source_img": "img3", "snapshot": (1778, 524, 62, 552), "paste": (16, 78, 20, 146)},
            {"type": "paste", "source_img": "img4", "snapshot": (1248, 2052, 546, 96), "paste": (1056, 462, 161, 30)},
        ]

        src_img3 = Image.open(image3_path).convert("RGB")
        src_img4 = Image.open(image4_path).convert("RGB")
        draw = ImageDraw.Draw(template)

        try:
            font = ImageFont.truetype("./NotoSansEthiopic-Bold.ttf", 18)
        except IOError:
            font = ImageFont.load_default()

        for reg in regions:
            x, y, w, h = reg["snapshot"]
            crop_box = (x, y, x + w, y + h)
            cropped = src_img3.crop(crop_box) if reg["source_img"]=="img3" else src_img4.crop(crop_box)

            if reg["type"] == "ocr":
                text = pytesseract.image_to_string(cropped, lang="eng").strip()
                log("Step 3", f"OCR result: '{text}'")
                if text:
                    draw.text(reg["paste"], text, font=font, fill=(0,0,0))
            else:
                p_x, p_y, p_w, p_h = reg["paste"]
                resized = cropped.resize((p_w, p_h), Image.Resampling.LANCZOS)
                template.paste(resized, (p_x, p_y))

        log("Step 3", "Done with image 3 & 4")
        return template
    except Exception as e:
        log("Step 3", f"Error: {e}")
        return None

# ---- TEXT BLOCKS ----
def write_pdf_blocks_on_template(pdf_doc, template_img):
    """Extracts text blocks from the PDF and writes them onto the template image."""
    log("Step 4", "Writing PDF text blocks...")
    block_to_png_mapping = [
        {"pdf_block_index": 29, "png_point": {"x": 355, "y": 268}},
        {"pdf_block_index": 30, "png_point": {"x": 355, "y": 324}},
        {"pdf_block_index": 31, "png_point": {"x": 960, "y": 146}},
        {"pdf_block_index": 32, "png_point": {"x": 960, "y": 67}},
        {"pdf_block_index": 33, "png_point": {"x": 960, "y": 200}},
        {"pdf_block_index": 34, "png_point": {"x": 960, "y": 255}},
        {"pdf_block_index": 35, "png_point": {"x": 960, "y": 380}},
        {"pdf_block_index": 37, "png_point": {"x": 355, "y": 158}},
    ]
    single_line_blocks = [29, 30, 31]

    try:
        font = ImageFont.truetype("./NotoSansEthiopic-Bold.ttf", 18)
    except IOError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(template_img)
    pdf_page = pdf_doc.load_page(0)
    pdf_text_blocks = pdf_page.get_text("blocks")

    for mapping in block_to_png_mapping:
        idx, point = mapping["pdf_block_index"], mapping["png_point"]
        if idx >= len(pdf_text_blocks):
            log("Step 4", f"Block {idx} out of range")
            continue
        text = pdf_text_blocks[idx][4].strip()
        if not text:
            log("Step 4", f"Block {idx} empty")
            continue

        if idx == 34:  # wrap logic
            words = text.split()
            if len(words) > 5:
                wrapped_words = [words[j:j+3] for j in range(0, len(words), 3)]
                text = "\n".join(" ".join(line) for line in wrapped_words)
                for block in block_to_png_mapping:
                    if block["pdf_block_index"] == 35:
                        block["png_point"]["y"] = 380
            else:
                for block in block_to_png_mapping:
                    if block["pdf_block_index"] == 35:
                        block["png_point"]["y"] = 362

        if idx in single_line_blocks:
            text = "|".join(text.split())

        draw.text((point["x"], point["y"]), text, fill="black", font=font)
        log("Step 4", f"Wrote block {idx}")

    # Special 7-digit extraction from block 36
    block_index_to_process = 36
    if block_index_to_process < len(pdf_text_blocks):
        full_text = pdf_text_blocks[block_index_to_process][4].strip()
        cleaned = full_text.replace(" ", "")
        if len(cleaned) >= 14:
            extracted_digits = (
                cleaned[1] + cleaned[2] +
                cleaned[4] + cleaned[5] +
                cleaned[8] + cleaned[9] +
                cleaned[13]
            )
            fan_point = {"x": 1677, "y": 511}
            draw.text((fan_point["x"], fan_point["y"]), extracted_digits, fill="black", font=font)
            log("Step 4", f"Extracted FAN digits: {extracted_digits}")

    log("Step 4", "Done writing text blocks")
    return template_img

def flip_and_place_on_a4(source_img_path, a4_template_path, output_path):
    """Flips the merged image horizontally and places it on an A4 template."""
    try:
        log("Step 5", "Flipping merged image and placing on A4 template...")

        src_img = Image.open(source_img_path)
        a4_template = Image.open(a4_template_path).convert("RGBA")

        flipped = ImageOps.mirror(src_img)

        target_x, target_y, target_w, target_h = 113, 47, 2189, 647
        resized = flipped.resize((target_w, target_h), Image.Resampling.LANCZOS)

        a4_template.paste(resized, (target_x, target_y), mask=resized)

        a4_template.save(output_path, "PNG")
        log("Step 5", f"✅ Saved flipped+A4 result: {output_path}")

    except Exception as e:
        log("Step 5", f"Error: {e}")

# ---- MAIN ----
def main_process(pdf_path, template_path, output_path, a4_template_path, output_a4_path):
    """Main function to run the entire PDF-to-image processing pipeline."""
    start_time = time.time()
    try:
        log("Main", "Opening PDF...")
        pdf_doc = fitz.open(pdf_path)
    except Exception as e:
        log("Main", f"Failed to open PDF: {e}")
        return

    images = extract_images(pdf_doc)
    if len(images) < 4:
        log("Main", "Less than 4 images found in PDF")
        return

    # MODIFIED: Pass the path to image_3.png (images[2]) to the function
    final_image = process_image1_and_2(pdf_doc, template_path, images[2])
    if not final_image: return

    final_image = process_image3_image4_with_ocr(final_image, images[2], images[3])
    if not final_image: return

    final_image = write_pdf_blocks_on_template(pdf_doc, final_image)

    try:
        final_image.save(output_path, "PNG")
        log("Main", f"✅ Saved merged output: {output_path}")
    except Exception as e:
        log("Main", f"Error saving merged output: {e}")
    finally:
        pdf_doc.close()

    # Step 5: Flip and place on A4
    flip_and_place_on_a4(output_path, a4_template_path, output_a4_path)

    log("Main", f"Finished in {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    # Define file paths
    input_pdf = "e2.pdf"
    template_image = "template_final.png"
    output_image = "merged_output.png"
    a4_template_image = "a4.png"
    output_a4 = "merged_output_on_a4.png"

    # Run the main process
    main_process(input_pdf, template_image, output_image, a4_template_image, output_a4)
