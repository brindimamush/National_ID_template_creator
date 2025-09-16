import os
import logging
import shutil
import asyncio
import uuid
#from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

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
REQUIRED_FILES = ["template_final.png", "a4.png"]

# --- Authorized users ---
AUTHORIZED_USERS = set()

def load_authorized_users():
    """Load authorized Telegram user IDs from environment variable TELEGRAM_USER_ID."""
    ids = os.getenv("ADMIN_IDS", "")
    if ids:
        try:
            AUTHORIZED_USERS.update(int(uid.strip()) for uid in ids.split(",") if uid.strip().isdigit())
            logger.info(f"Authorized users set to: {AUTHORIZED_USERS}")
        except Exception as e:
            logger.error(f"Failed to parse TELEGRAM_USER_ID: {e}")
    else:
        logger.warning("No TELEGRAM_USER_ID set in environment!")

def is_authorized(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return ConversationHandler.END

    missing_files = [f for f in REQUIRED_FILES if not os.path.exists(f)]
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

    # ✅ Per-job unique folder
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(".temp_jobs", f"{user_id}_{job_id}")
    os.makedirs(job_dir, exist_ok=True)

    input_pdf_path = os.path.join(job_dir, "input.pdf")
    output_files_to_send = []

    try:
        # Download file
        pdf_file = await context.bot.get_file(doc.file_id)
        await pdf_file.download_to_drive(input_pdf_path)
        await update.message.reply_text("📥 PDF received. Processing has started...")

        user_choice = context.user_data.get("choice")

        # COLOR
        if user_choice in ["color", "both"]:
            await update.message.reply_text("🎨 Running color processing...")
            merged_output_path = os.path.join(job_dir, "NID_color.png")
            final_output_path = os.path.join(job_dir, "NIDA4_color.png")

            try:
                await asyncio.to_thread(
                    main_process_color,
                    input_pdf_path,
                    "template_final.png",
                    merged_output_path,
                    "a4.png",
                    final_output_path,
                )
                await update.message.reply_text("✅ Color processing finished.")
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in color processing for user {user_id}: {e}", exc_info=True)
                await update.message.reply_text("❌ An error occurred during 'color' processing.")

        # BLACK
        if user_choice in ["black", "both"]:
            await update.message.reply_text("🖤 Running black & white processing...")
            merged_output_path = os.path.join(job_dir, "NID_black.png")
            final_output_path = os.path.join(job_dir, "NIDA4_black.png")

            try:
                await asyncio.to_thread(
                    main_process_black,
                    input_pdf_path,
                    "template_final.png",
                    merged_output_path,
                    "a4.png",
                    final_output_path,
                )
                await update.message.reply_text("✅ Black & white processing finished.")
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in black processing for user {user_id}: {e}", exc_info=True)
                await update.message.reply_text("❌ An error occurred during 'black' processing.")

        # Send outputs
        if output_files_to_send:
            await update.message.reply_text("📤 Sending your file(s)...")
            for file_path in output_files_to_send:
                try:
                    await context.bot.send_chat_action(
                        chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT
                    )
                    with open(file_path, "rb") as doc_file:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=doc_file,
                            filename=os.path.basename(file_path),
                        )
                except Exception as e:
                    logger.error(f"Error sending file {file_path} to user {user_id}: {e}")
                    await update.message.reply_text(f"⚠️ Failed to send {os.path.basename(file_path)}.")
        else:
            await update.message.reply_text("⚠️ Could not generate any output files. Please try again.")

    except Exception as e:
        logger.error(f"Critical error for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Critical error: {type(e).__name__} - {e}")
    finally:
        # ✅ Cleanup unique job folder
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Error cleaning up job folder {job_dir}: {e}")

    await update.message.reply_text("🎉 All done! Use /start to process another file.")
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

# --- Global Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    if update and hasattr(update, "message") and update.message:
        try:
            await update.message.reply_text("❌ An internal error occurred. Please try again.")
        except Exception:
            pass

# --- Main ---
def main() -> None:
    #load_dotenv()

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
    application.add_error_handler(error_handler)

    logger.info("Bot started and is polling for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()
