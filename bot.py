import os
import logging
import shutil
import tempfile
import asyncio
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from PIL import Image

# Heavy image-processing functions (synchronous)
from flippedcolor import main_process as main_process_color
from flippedblack import main_process as main_process_black

# --- Logging setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation states ---
CHOOSING, PDF_UPLOAD = range(2)

# --- Config ---
MAX_FILE_SIZE = 50 * 1024 * 1024
TEMPLATE_FILES = ["template_final.png", "a4.png"]
FONT_FILE = "NotoSansEthiopic-Bold.ttf"

# --- Authorized users ---
AUTHORIZED_USERS = set()

def load_authorized_users():
    """Load authorized Telegram user IDs from environment variable TELEGRAM_USER_IDS."""
    ids = os.getenv("TELEGRAM_USER_ID", "")
    if ids:
        try:
            AUTHORIZED_USERS.update(int(uid.strip()) for uid in ids.split(",") if uid.strip().isdigit())
            logger.info(f"Authorized users set to: {AUTHORIZED_USERS}")
        except Exception as e:
            logger.error(f"Failed to parse TELEGRAM_USER_IDS: {e}")
    else:
        logger.warning("No TELEGRAM_USER_IDS set in environment!")

def is_authorized(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS

def setup_user_workspace(user_id: int, file_id: str) -> dict:
    """
    Create a temporary workspace for the user and copy required files.
    Returns dictionary with paths to all required files.
    """
    workspace_dir = f"workspace_{user_id}_{file_id}"
    os.makedirs(workspace_dir, exist_ok=True)
    
    file_paths = {
        'workspace_dir': workspace_dir,
        'input_pdf': f"{workspace_dir}/input.pdf"
    }
    
    # Copy template files
    for template_file in TEMPLATE_FILES:
        if os.path.exists(template_file):
            dest_path = f"{workspace_dir}/{template_file}"
            shutil.copy2(template_file, dest_path)
            file_paths[template_file.split('.')[0]] = dest_path
    
    # Copy font file if it exists
    if os.path.exists(FONT_FILE):
        dest_font_path = f"{workspace_dir}/{FONT_FILE}"
        shutil.copy2(FONT_FILE, dest_font_path)
        file_paths['font'] = dest_font_path
    
    return file_paths

def cleanup_workspace(workspace_dir: str):
    """Clean up the temporary workspace directory."""
    if os.path.exists(workspace_dir):
        try:
            shutil.rmtree(workspace_dir)
        except Exception as e:
            logger.error(f"Error removing workspace {workspace_dir}: {e}")

# --- Worker function for heavy processing ---
async def process_pdf_task(
    chat_id: int,
    user_id: int,
    file_id: str,
    user_choice: str,
    workspace_paths: dict,
    bot_app: Application
):
    """
    This is the heavy-duty worker function that runs in a separate thread.
    It performs all the processing and sends the files.
    """
    output_files_to_send = []

    try:
        # COLOR
        if user_choice in ["color", "both"]:
            await bot_app.bot.send_message(chat_id, "🎨 Running color processing...")
            merged_output_path = f"{workspace_paths['workspace_dir']}/NID_color_{file_id}.png"
            final_output_path = f"{workspace_paths['workspace_dir']}/NIDA4_color_{file_id}.png"

            try:
                await asyncio.to_thread(
                    main_process_color,
                    workspace_paths['input_pdf'],
                    workspace_paths['template_final'],
                    merged_output_path,
                    workspace_paths['a4'],
                    final_output_path,
                )
                await bot_app.bot.send_message(chat_id, "✅ Color processing finished.")
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in color processing for user {user_id}: {e}", exc_info=True)
                await bot_app.bot.send_message(chat_id, "❌ An error occurred during 'color' processing.")

        # BLACK
        if user_choice in ["black", "both"]:
            await bot_app.bot.send_message(chat_id, "🖤 Running black & white processing...")
            merged_output_path = f"{workspace_paths['workspace_dir']}/NID_black_{file_id}.png"
            final_output_path = f"{workspace_paths['workspace_dir']}/NIDA4_black_{file_id}.png"

            try:
                await asyncio.to_thread(
                    main_process_black,
                    workspace_paths['input_pdf'],
                    workspace_paths['template_final'],
                    merged_output_path,
                    workspace_paths['a4'],
                    final_output_path,
                )
                await bot_app.bot.send_message(chat_id, "✅ Black & white processing finished.")
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in black processing for user {user_id}: {e}", exc_info=True)
                await bot_app.bot.send_message(chat_id, "❌ An error occurred during 'black' processing.")

        # Send outputs
        if output_files_to_send:
            await bot_app.bot.send_message(chat_id, "📤 Sending your file(s)...")
            
            # --- New: Compress PNG and send it as a PNG document ---
            for file_path in output_files_to_send:
                compressed_path = file_path.replace(".png", "_compressed.png")
                try:
                    with Image.open(file_path) as img:
                        # Save with optimize=True for lossless compression
                        img.save(compressed_path, "PNG", optimize=True)

                    # Send the compressed PNG file
                    with open(compressed_path, "rb") as doc_file:
                        await bot_app.bot.send_document(
                            chat_id=chat_id,
                            document=doc_file,
                            filename=os.path.basename(compressed_path),
                        )
                except Exception as e:
                    logger.error(f"Error sending or compressing file {file_path} to user {user_id}: {e}", exc_info=True)
                    await bot_app.bot.send_message(chat_id, f"⚠️ Failed to send {os.path.basename(file_path)}.")
                finally:
                    # Clean up the compressed file
                    if os.path.exists(compressed_path):
                        os.remove(compressed_path)

        else:
            await bot_app.bot.send_message(chat_id, "⚠️ Could not generate any output files. Please try again.")

    except Exception as e:
        logger.error(f"Critical error in worker for user {user_id}: {e}", exc_info=True)
        await bot_app.bot.send_message(chat_id, "❌ A critical error occurred during processing.")
    finally:
        # Cleanup
        cleanup_workspace(workspace_paths['workspace_dir'])
        temp_img_dir = ".temp"
        if os.path.isdir(temp_img_dir):
            try:
                shutil.rmtree(temp_img_dir)
            except Exception as e:
                logger.error(f"Error removing temp directory {temp_img_dir}: {e}")

    await bot_app.bot.send_message(chat_id, "🎉 All done! Use /start to process another file.")

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return ConversationHandler.END

    missing_files = [f for f in TEMPLATE_FILES if not os.path.exists(f)]
    if missing_files:
        await update.message.reply_text(
            f"❌ Missing required files: {', '.join(missing_files)}. Contact admin."
        )
        return ConversationHandler.END

    reply_keyboard = [["Color", "Black", "Both"]]
    await update.message.reply_text(
        "👋 Hi! I am the NID PDF to PNG Processor Bot.\n\n"
        "Please choose an option:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSING

async def choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized access.")
        return ConversationHandler.END

    user_choice = update.message.text
    context.user_data["choice"] = user_choice.lower()
    await update.message.reply_text(
        f'Excellent! You chose "{user_choice}".\nNow, please upload your PDF file.',
        reply_markup=ReplyKeyboardRemove(),
    )
    return PDF_UPLOAD

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return ConversationHandler.END

    doc = update.message.document
    if not doc or doc.mime_type != "application/pdf":
        await update.message.reply_text("⚠️ Please upload a valid PDF file.")
        return PDF_UPLOAD

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"⚠️ This file is too large. Maximum allowed size is {MAX_FILE_SIZE // (1024*1024)}MB."
        )
        return PDF_UPLOAD

    safe_file_id = f"{user_id}_{''.join(c for c in doc.file_id if c.isalnum() or c in ('-', '_'))}"

    # Setup user workspace
    workspace_paths = setup_user_workspace(user_id, safe_file_id)
    user_choice = context.user_data.get("choice")

    try:
        # Download file to workspace
        pdf_file = await context.bot.get_file(doc.file_id)
        await pdf_file.download_to_drive(workspace_paths['input_pdf'])
        
        # Immediately acknowledge the request
        await update.message.reply_text("📥 PDF received. Your request has been queued and will be processed shortly.")
        await update.message.reply_text("I will send the result as soon as it's ready. Please be patient.")

        # Offload the heavy work to a separate task
        asyncio.create_task(
            process_pdf_task(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                file_id=safe_file_id,
                user_choice=user_choice,
                workspace_paths=workspace_paths,
                bot_app=context.application,
            )
        )

    except Exception as e:
        logger.error(f"Critical error for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ A critical error occurred during file reception.")
        # Cleanup if download failed
        cleanup_workspace(workspace_paths['workspace_dir'])
        return ConversationHandler.END

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text("❌ Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("FATAL: TELEGRAM_BOT_TOKEN not found in environment!")
        return

    load_authorized_users()

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.Regex("^(Color|Black|Both)$"), choice)],
            PDF_UPLOAD: [MessageHandler(filters.Document.PDF, handle_pdf)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    logger.info("Bot started and is polling for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()
