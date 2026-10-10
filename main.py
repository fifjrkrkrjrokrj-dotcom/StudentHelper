import os
import math
import asyncio
import tempfile
import traceback
from pathlib import Path
from dotenv import load_dotenv

import pymupdf as fitz
from PIL import Image, ImageOps
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)

# Load environment variables from .env file if it exists
load_dotenv()

API_ID = int(os.getenv("API_ID", "34177205"))
API_HASH = os.getenv("API_HASH", "fa5c4b5a6dde337c31addb5240e9c205")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8999665775:AAFlIk42x_-F7jx2Gm2cvRipdqQ_xE_sU94")

app = Client(
    "StudyHelperBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

PDF_SEMAPHORE = asyncio.Semaphore(2)

user_image_queues = {}
user_pdf_states = {}

# =========================================================================
# 📄 UTILS & PDF PROCESSING
# =========================================================================

def get_pdf_options_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖨️ Optimize for Print", callback_data="menu:print_opt")],
        [InlineKeyboardButton("🖼️ Convert to Images", callback_data="cv:pdf2img")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cv:cancel")]
    ])

def get_print_layout_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 1-in-1 (B&W)", callback_data="cv:1_bw"),
            InlineKeyboardButton("🎨 1-in-1 (Color Invert)", callback_data="cv:1_color"),
        ],
        [InlineKeyboardButton("📑 2-in-1 Landscape", callback_data="cv:2_land")],
        [InlineKeyboardButton("📄 2-in-1 Portrait", callback_data="cv:2_port")],
        [InlineKeyboardButton("🔲 Custom N-in-1 Grid", callback_data="cv:custom_grid")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu:main")],
    ])

def process_page(page, dpi=150, color_mode="bw"):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    gray = ImageOps.grayscale(img)
    small = gray.resize((min(200, gray.width), min(200, gray.height)))
    hist = small.histogram()
    total = sum(hist)
    cum = 0
    median = 0
    for val, count in enumerate(hist):
        cum += count
        if cum >= total / 2:
            median = val
            break
            
    is_dark_bg = median < 128

    if color_mode == "color":
        if is_dark_bg:
            img = ImageOps.invert(img)
        return img
    else:
        if is_dark_bg:
            gray = ImageOps.invert(gray)
        bw = gray.point(lambda p: 255 if p > 160 else 0, mode="1")
        return bw.convert("RGB")

def convert_pdf_advanced(src, dst, layout="1_bw", progress_callback=None):
    src_doc = fitz.open(src)
    out_doc = fitz.open()
    color_mode = "color" if layout == "1_color" else "bw"

    try:
        total = len(src_doc)
        if progress_callback: progress_callback(0, total)

        A4_W, A4_H = 595.28, 841.89

        if layout in ("1_bw", "1_color"):
            for i, page in enumerate(src_doc):
                img = process_page(page, dpi=150, color_mode=color_mode)
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                try:
                    img.save(tmp.name, format="PNG", optimize=True)
                    new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                    new_page.insert_image(new_page.rect, filename=tmp.name, keep_proportion=True)
                finally:
                    if os.path.exists(tmp.name): os.unlink(tmp.name)
                if progress_callback: progress_callback(i + 1, total)

        elif layout == "2_land":
            sheet_w, sheet_h = A4_H, A4_W
            margin, gap = 15, 12
            half_w = (sheet_w - 2 * margin - gap) / 2
            h_box = sheet_h - 2 * margin
            rect_left = fitz.Rect(margin, margin, margin + half_w, margin + h_box)
            rect_right = fitz.Rect(margin + half_w + gap, margin, sheet_w - margin, margin + h_box)
            divider_x = margin + half_w + (gap / 2)

            for i in range(0, total, 2):
                new_page = out_doc.new_page(width=sheet_w, height=sheet_h)
                new_page.draw_line(fitz.Point(divider_x, margin + 5), fitz.Point(divider_x, sheet_h - margin - 5), color=(0.85, 0.85, 0.85), width=0.5)

                p1 = src_doc[i]
                img1 = process_page(p1, dpi=150, color_mode=color_mode)
                tmp1 = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp1.close()
                try:
                    img1.save(tmp1.name, format="PNG", optimize=True)
                    new_page.insert_image(rect_left, filename=tmp1.name, keep_proportion=True)
                finally:
                    if os.path.exists(tmp1.name): os.unlink(tmp1.name)

                if i + 1 < total:
                    p2 = src_doc[i + 1]
                    img2 = process_page(p2, dpi=150, color_mode=color_mode)
                    tmp2 = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp2.close()
                    try:
                        img2.save(tmp2.name, format="PNG", optimize=True)
                        new_page.insert_image(rect_right, filename=tmp2.name, keep_proportion=True)
                    finally:
                        if os.path.exists(tmp2.name): os.unlink(tmp2.name)

                if progress_callback: progress_callback(min(i + 2, total), total)

        elif layout == "2_port":
            sheet_w, sheet_h = A4_W, A4_H
            margin, gap = 15, 12
            half_h = (sheet_h - 2 * margin - gap) / 2
            w_box = sheet_w - 2 * margin
            rect_top = fitz.Rect(margin, margin, margin + w_box, margin + half_h)
            rect_bottom = fitz.Rect(margin, margin + half_h + gap, margin + w_box, sheet_h - margin)
            divider_y = margin + half_h + (gap / 2)

            for i in range(0, total, 2):
                new_page = out_doc.new_page(width=sheet_w, height=sheet_h)
                new_page.draw_line(fitz.Point(margin + 5, divider_y), fitz.Point(sheet_w - margin - 5, divider_y), color=(0.85, 0.85, 0.85), width=0.5)

                p1 = src_doc[i]
                img1 = process_page(p1, dpi=150, color_mode=color_mode)
                tmp1 = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp1.close()
                try:
                    img1.save(tmp1.name, format="PNG", optimize=True)
                    new_page.insert_image(rect_top, filename=tmp1.name, keep_proportion=True)
                finally:
                    if os.path.exists(tmp1.name): os.unlink(tmp1.name)

                if i + 1 < total:
                    p2 = src_doc[i + 1]
                    img2 = process_page(p2, dpi=150, color_mode=color_mode)
                    tmp2 = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp2.close()
                    try:
                        img2.save(tmp2.name, format="PNG", optimize=True)
                        new_page.insert_image(rect_bottom, filename=tmp2.name, keep_proportion=True)
                    finally:
                        if os.path.exists(tmp2.name): os.unlink(tmp2.name)

                if progress_callback: progress_callback(min(i + 2, total), total)

        elif layout.startswith("grid_"):
            n_pages = int(layout.split("_")[1])
            sheet_w, sheet_h = A4_W, A4_H
            margin, gap = 15, 10
            
            cols = math.ceil(math.sqrt(n_pages))
            rows = math.ceil(n_pages / cols)
            if cols > rows:
                cols, rows = rows, cols
                
            cell_w = (sheet_w - 2 * margin - (cols - 1) * gap) / cols
            cell_h = (sheet_h - 2 * margin - (rows - 1) * gap) / rows

            rects = []
            for r in range(rows):
                for c in range(cols):
                    x0 = margin + c * (cell_w + gap)
                    y0 = margin + r * (cell_h + gap)
                    x1 = x0 + cell_w
                    y1 = y0 + cell_h
                    rects.append(fitz.Rect(x0, y0, x1, y1))

            for i in range(0, total, n_pages):
                new_page = out_doc.new_page(width=sheet_w, height=sheet_h)
                for slot in range(n_pages):
                    idx = i + slot
                    if idx < total and slot < len(rects):
                        p = src_doc[idx]
                        img = process_page(p, dpi=150, color_mode=color_mode)
                        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                        tmp.close()
                        try:
                            img.save(tmp.name, format="PNG", optimize=True)
                            new_page.insert_image(rects[slot], filename=tmp.name, keep_proportion=True)
                        finally:
                            if os.path.exists(tmp.name): os.unlink(tmp.name)
                if progress_callback: progress_callback(min(i + n_pages, total), total)

        out_doc.save(dst, garbage=4, deflate=True)
    finally:
        out_doc.close()
        src_doc.close()

def create_pdf_from_images(image_paths, output_pdf):
    doc = fitz.open()
    for img_path in image_paths:
        img = fitz.open(img_path)
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close()
        
        img_pdf = fitz.open("pdf", pdfbytes)
        page = doc.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(rect, img_pdf, 0)
        img_pdf.close()
    
    doc.save(output_pdf)
    doc.close()

# =========================================================================
# 🤖 BOT HANDLERS
# =========================================================================

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    await message.reply_text(
        "👋 **Namaste! Main hu aapka Study Helper Bot** 📚\n\n"
        "✨ **Available Features:**\n\n"
        "🖼️ **1. Image to PDF:**\n"
        "• Mujhe koi bhi images bhejein.\n"
        "• Phir 'Generate PDF' pe click karein.\n\n"
        "📄 **2. PDF Print Optimizer & Tools:**\n"
        "• Koi bhi PDF send karein.\n"
        "• **PDF to Image**: Extract all pages as images.\n"
        "• **1-in-1 B&W / Color Invert** (Dark Background ➔ Clean White)\n"
        "• **2-in-1 Landscape & Portrait**\n"
        "• **🔲 Custom N-in-1 Grid** (Jaise 4, 6, 9 pages per sheet)\n\n"
        "🚀 _Try karne ke liye koi PDF ya Images bhejiye!_"
    )

@app.on_message(filters.photo)
async def photo_received_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_image_queues:
        user_image_queues[user_id] = []
    
    user_image_queues[user_id].append(message.photo.file_id)
    count = len(user_image_queues[user_id])
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Generate PDF", callback_data="img2pdf:generate")],
        [InlineKeyboardButton("❌ Cancel", callback_data="img2pdf:cancel")]
    ])
    
    await message.reply_text(
        f"📸 **Image Received!**\nTotal images added: `{count}`\n\nAap aur bhi images bhej sakte hain, ya 'Generate PDF' pe click karein.",
        reply_markup=keyboard,
        quote=True
    )

@app.on_callback_query(filters.regex(r"^img2pdf:"))
async def img2pdf_callback(client: Client, callback_query: CallbackQuery):
    action = callback_query.data.split(":")[1]
    user_id = callback_query.from_user.id
    
    if action == "cancel":
        if user_id in user_image_queues: del user_image_queues[user_id]
        await callback_query.message.edit_text("❌ Image to PDF conversion cancel kar diya gaya.")
        return
        
    if action == "generate":
        if user_id not in user_image_queues or not user_image_queues[user_id]:
            await callback_query.message.edit_text("❌ Koi images nahi hain convert karne ke liye.")
            return
            
        images = user_image_queues[user_id]
        status = await callback_query.message.edit_text(f"⏳ Processing `{len(images)}` images into PDF...")
        
        async with PDF_SEMAPHORE:
            with tempfile.TemporaryDirectory() as work:
                img_paths = []
                try:
                    for i, file_id in enumerate(images):
                        path = os.path.join(work, f"img_{i}.jpg")
                        await client.download_media(file_id, file_name=path)
                        img_paths.append(path)
                    
                    out_pdf = os.path.join(work, "Generated_Document.pdf")
                    await asyncio.to_thread(create_pdf_from_images, img_paths, out_pdf)
                    
                    await client.send_chat_action(callback_query.message.chat.id, enums.ChatAction.UPLOAD_DOCUMENT)
                    await callback_query.message.reply_document(document=out_pdf, file_name="Generated_Notes.pdf", caption="✅ **Yeh lijiye aapki PDF!**")
                    await status.delete()
                    if user_id in user_image_queues: del user_image_queues[user_id]
                except Exception as e:
                    traceback.print_exc()
                    await status.edit_text(f"❌ Error while generating PDF: `{e}`")

@app.on_message(filters.document)
async def pdf_received_handler(client: Client, message: Message):
    document = message.document
    if not (document.file_name and document.file_name.lower().endswith(".pdf")) and document.mime_type != "application/pdf":
        await message.reply_text("❌ Sirf PDF file bhejein (Images ke liye direct photo format me send karein).")
        return

    size_mb = (document.file_size or 0) / (1024 * 1024)
    file_name = document.file_name or "document.pdf"

    await message.reply_text(
        text=f"📁 **PDF Received:** `{file_name}`\n📦 **Size:** `{size_mb:.1f} MB`\n\n👇 **Kya karna chahte hain aap?**",
        reply_markup=get_pdf_options_keyboard(),
        quote=True
    )

@app.on_message(filters.text & ~filters.command("start"))
async def text_received_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_pdf_states:
        state_data = user_pdf_states[user_id]
        if message.text.isdigit():
            n = int(message.text)
            if n <= 0 or n > 100:
                await message.reply_text("❌ Kripya 1 se 100 ke beech ka number dalein.")
                return
            
            doc_msg = state_data["doc_msg"]
            del user_pdf_states[user_id]
            layout = f"grid_{n}"
            status_msg = await message.reply_text(f"🎯 **Mode Selected:** `{n}-in-1 Custom Grid`\n📥 **Download shuru ho rahi hai...**")
            await run_pdf_conversion(client, status_msg, doc_msg, layout, f"{n}-in-1 Custom Grid")
        else:
            await message.reply_text("❌ Kripya valid number bhejein (jaise: 4, 6, 9).")

@app.on_callback_query(filters.regex(r"^menu:"))
async def menu_handler(client: Client, callback_query: CallbackQuery):
    action = callback_query.data.split(":")[1]
    if action == "print_opt":
        await callback_query.message.edit_text("🖨️ **Select layout for Print Optimization:**", reply_markup=get_print_layout_keyboard())
    elif action == "main":
        await callback_query.message.edit_text("👇 **Kya karna chahte hain aap?**", reply_markup=get_pdf_options_keyboard())

@app.on_callback_query(filters.regex(r"^cv:"))
async def callback_handler(client: Client, callback_query: CallbackQuery):
    action = callback_query.data.split(":")[1]

    if action == "cancel":
        await callback_query.message.edit_text("❌ Action cancelled.")
        return

    doc_msg = callback_query.message.reply_to_message
    if not doc_msg or not doc_msg.document:
        await callback_query.message.edit_text("❌ Original PDF message nahi mila. Kripya PDF dobara bhejein.")
        return

    if action == "custom_grid":
        user_pdf_states[callback_query.from_user.id] = {"doc_msg": doc_msg}
        await callback_query.message.edit_text("🔢 **Kitne pages 1 sheet pe chahiye?**\n\nNeeche number type karke mujhe bhejein (jaise: 4, 6, 9, 16):")
        return

    document = doc_msg.document

    if action == "pdf2img":
        status = await callback_query.message.edit_text("⏳ **Extracting images from PDF...**")
        async with PDF_SEMAPHORE:
            with tempfile.TemporaryDirectory() as work:
                src = os.path.join(work, "input.pdf")
                try:
                    await client.download_media(doc_msg, file_name=src)
                    
                    def extract_images(pdf_path, out_dir):
                        doc = fitz.open(pdf_path)
                        paths = []
                        for i in range(len(doc)):
                            page = doc[i]
                            pix = page.get_pixmap(dpi=200)
                            img_path = os.path.join(out_dir, f"page_{i+1}.jpg")
                            pix.save(img_path)
                            paths.append(img_path)
                        doc.close()
                        return paths
                    
                    img_paths = await asyncio.to_thread(extract_images, src, work)
                    
                    if not img_paths:
                        await status.edit_text("❌ PDF mein koi page nahi hai ya invalid PDF hai.")
                        return
                    
                    await status.edit_text(f"📤 **Uploading {len(img_paths)} images...**")
                    await client.send_chat_action(doc_msg.chat.id, enums.ChatAction.UPLOAD_PHOTO)
                    
                    for i in range(0, len(img_paths), 10):
                        chunk = img_paths[i:i+10]
                        media = [InputMediaPhoto(p) for p in chunk]
                        await doc_msg.reply_media_group(media)
                        
                    await status.delete()
                except Exception as e:
                    traceback.print_exc()
                    await status.edit_text(f"❌ Error during extraction: `{e}`")
        return

    layout_titles = {
        "1_bw": "1-in-1 Normal B&W",
        "1_color": "1-in-1 Color Invert",
        "2_land": "2-in-1 Landscape (Side-by-Side)",
        "2_port": "2-in-1 Portrait (Top & Bottom)",
    }
    selected_title = layout_titles.get(action, "Custom Layout")
    status = await callback_query.message.edit_text(f"🎯 **Mode Selected:** `{selected_title}`\n📥 **Download shuru ho rahi hai...**")
    await run_pdf_conversion(client, status, doc_msg, action, selected_title)

async def run_pdf_conversion(client, status_msg, doc_msg, layout, selected_title):
    document = doc_msg.document
    state = {"stage": "downloading", "current": 0, "total": document.file_size or 0, "done": False}

    def dl_progress(current, total): state["current"] = current; state["total"] = total
    def proc_progress(current, total): state["current"] = current; state["total"] = total
    def up_progress(current, total): state["current"] = current; state["total"] = total

    async def progress_reporter():
        last_text = ""
        while not state["done"]:
            await asyncio.sleep(2.5)
            if state["done"]: break
            stg = state["stage"]
            curr = state["current"]
            tot = state["total"]

            if stg == "downloading" and tot > 0: text = f"🎯 **Mode:** `{selected_title}`\n📥 **Downloading PDF...**\nProgress: `{(curr/tot)*100:.1f}%`"
            elif stg == "processing" and tot > 0: text = f"🎯 **Mode:** `{selected_title}`\n⚙️ **Processing Pages...**\nPages: `{curr}/{tot}` ({int((curr/tot)*100)}%)\n_Applying layout..._"
            elif stg == "uploading" and tot > 0: text = f"🎯 **Mode:** `{selected_title}`\n📤 **Uploading Result...**\nProgress: `{(curr/tot)*100:.1f}%`"
            else: text = f"🎯 **Mode:** `{selected_title}`\n⚙️ **{stg.title()}...**"

            if text != last_text:
                try: await status_msg.edit_text(text); last_text = text
                except Exception: pass

    reporter_task = asyncio.create_task(progress_reporter())

    async with PDF_SEMAPHORE:
        with tempfile.TemporaryDirectory() as work:
            src = Path(work) / "input.pdf"
            dst = Path(work) / f"{layout}_ready.pdf"
            try:
                state["stage"] = "downloading"
                await client.download_media(doc_msg, file_name=str(src), progress=dl_progress)

                state["stage"] = "processing"; state["current"] = 0; state["total"] = 0
                await asyncio.to_thread(convert_pdf_advanced, src, dst, layout, proc_progress)

                state["stage"] = "uploading"; state["current"] = 0
                state["total"] = os.path.getsize(dst) if dst.exists() else 0

                await client.send_chat_action(doc_msg.chat.id, enums.ChatAction.UPLOAD_DOCUMENT)
                out_name = f"converted_{layout}_{document.file_name or 'notes.pdf'}"
                await doc_msg.reply_document(document=str(dst), file_name=out_name, caption=f"✅ **PDF Successfully Converted!**\n📐 **Layout:** `{selected_title}`\n🖨️ **Print Ready**", progress=up_progress)
                state["done"] = True; await reporter_task
                try: await status_msg.delete()
                except Exception: pass
            except Exception as e:
                state["done"] = True; await reporter_task
                traceback.print_exc()
                try: await status_msg.edit_text(f"❌ **Error:** `{type(e).__name__}: {e}`")
                except Exception: pass

if __name__ == "__main__":
    print("Starting Study Helper Bot...")
    app.run()
