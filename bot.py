import os
import logging
import shutil
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

# Assuming these are synchronous functions that do heavy image processing
from flippedcolor import main_process as main_process_color
from flippedblack import main_process as main_process_black

# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States ---
CHOOSING, PDF_UPLOAD = range(2)

# --- Configuration ---
MAX_FILE_SIZE = 50 * 1024 * 1024
REQUIRED_FILES = ["template_final.png", "a4.png"]


# --- Conversation Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and checks for required files."""
    missing_files = [f for f in REQUIRED_FILES if not os.path.exists(f)]
    if missing_files:
        await update.message.reply_text(
            f"❌ Missing required files: {', '.join(missing_files)}. Contact admin."
        )
        return ConversationHandler.END

    reply_keyboard = [['Color', 'Black', 'Both']]
    await update.message.reply_text(
        'Hi! I am the NID PDF to PNG Processor Bot.\n\n'
        'Please choose an option:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSING

async def choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the user's choice and asks for the PDF file."""
    user_choice = update.message.text
    context.user_data['choice'] = user_choice.lower()
    await update.message.reply_text(
        f'Excellent! You chose "{user_choice}".\nNow, please upload your PDF file.',
        reply_markup=ReplyKeyboardRemove(),
    )
    return PDF_UPLOAD

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the PDF file upload and processing without blocking."""
    user = update.effective_user

    doc = update.message.document
    if not doc or doc.mime_type != 'application/pdf':
        await update.message.reply_text('⚠️ Please upload a valid PDF file.')
        return PDF_UPLOAD
    
    if doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f'⚠️ This file is too large. Maximum allowed size is {MAX_FILE_SIZE // (1024*1024)}MB.'
        )
        return PDF_UPLOAD

    # --- File Download ---
    safe_file_id = f"{user.id}_{''.join(c for c in doc.file_id if c.isalnum() or c in ('-', '_'))}"
    input_pdf_path = f'{safe_file_id}.pdf'
    
    temp_files_to_clean = [input_pdf_path]
    output_files_to_send = []

    try:
        pdf_file = await context.bot.get_file(doc.file_id)
        await pdf_file.download_to_drive(input_pdf_path)
        await update.message.reply_text('✅ PDF received. Processing has started...')

        user_choice = context.user_data.get('choice')

        # --- Run processing based on user's choice ---
        if user_choice in ['color', 'both']:
            await update.message.reply_text('⏳ Starting color processing...')
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"NID_color_{safe_file_id}.png"
            final_output_path = f"NIDA4_color_{safe_file_id}.png"
            temp_files_to_clean.extend([merged_output_path, final_output_path])
            
            try:
                # IMPORTANT: Run the blocking function in a separate thread
                await asyncio.to_thread(
                    main_process_color, 
                    input_pdf_path, template_path, merged_output_path, a4_template_path, final_output_path
                )
                await update.message.reply_text('✅ Color processing finished.')
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in color processing for user {user.id}: {e}", exc_info=True)
                await update.message.reply_text("An error occurred during 'color' processing.")

        if user_choice in ['black', 'both']:
            await update.message.reply_text('⏳ Starting black & white processing...')
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"NID_black_{safe_file_id}.png"
            final_output_path = f"NIDA4_black_{safe_file_id}.png"
            temp_files_to_clean.extend([merged_output_path, final_output_path])

            try:
                # IMPORTANT: Run the blocking function in a separate thread
                await asyncio.to_thread(
                    main_process_black,
                    input_pdf_path, template_path, merged_output_path, a4_template_path, final_output_path
                )
                await update.message.reply_text('✅ Black & white processing finished.')
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
            except Exception as e:
                logger.error(f"Error in black processing for user {user.id}: {e}", exc_info=True)
                await update.message.reply_text("An error occurred during 'black' processing.")

        # --- Send the final image(s) back to the user ---
        if output_files_to_send:
            await update.message.reply_text('📤 Sending your file(s)...')
            for file_path in output_files_to_send:
                try:
                    with open(file_path, 'rb') as doc_file:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=doc_file,
                            filename=os.path.basename(file_path)
                        )
                except Exception as e:
                    logger.error(f"Error sending file {file_path} to user {user.id}: {e}")
                    await update.message.reply_text(f"Failed to send {os.path.basename(file_path)}.")
        else:
            await update.message.reply_text('Could not generate any output files. Please check the PDF and try again.')

    except Exception as e:
        logger.error(f"A critical error occurred for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text('A critical error occurred. The operation has been stopped.')
    finally:
        # --- Cleanup all temporary files ---
        logger.info(f"Cleaning up temporary files for user {user.id}...")
        for temp_file in temp_files_to_clean:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    logger.error(f"Error removing temp file {temp_file}: {e}")
        
        temp_img_dir = ".temp"
        if os.path.isdir(temp_img_dir):
            try:
                shutil.rmtree(temp_img_dir)
            except Exception as e:
                logger.error(f"Error removing temp directory {temp_img_dir}: {e}")

    await update.message.reply_text('All done! Use /start to process another file.')
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        'Operation cancelled.', reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Main Bot Execution ---
def main() -> None:
    """Sets up and runs the bot."""
    # It's recommended to use python-dotenv to load these
    # from a .env file, but direct os.getenv is fine.
    # from dotenv import load_dotenv
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("FATAL: TELEGRAM_BOT_KEY not found in environment!")
        return
        
    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.Regex('^(Color|Black|Both)$'), choice)],
            PDF_UPLOAD: [MessageHandler(filters.Document.PDF, handle_pdf)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    logger.info("Bot started and is polling for updates...")
    application.run_polling()


if __name__ == '__main__':
    main()

