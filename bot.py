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

# --- IMPORTANT ---
# Make sure the following files are in the same directory as this bot.py file:
# - flippedcolor.py
# - flippedblack.py
# - template_final.png
# - a4.png
# - NotoSansEthiopic-Bold.ttf (or another font file if you changed it)
from flippedcolor import main_process as main_process_color
from flippedblack import main_process as main_process_black

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define states for conversation
CHOOSING, PDF_UPLOAD = range(2)

# Maximum file size in bytes (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Required files for processing
REQUIRED_FILES = ["template_final.png", "a4.png"]

# List of authorized user IDs (replace with your actual user IDs)
# You can get your user ID by sending a message to @userinfobot on Telegram
AUTHORIZED_USERS = [1279032438]  # Replace with your actual user IDs

# Function to check if user is authorized
def is_authorized(user_id: int) -> bool:
    """Check if the user is authorized to use the bot."""
    return user_id in AUTHORIZED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks for user's choice."""
    # Check if user is authorized
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this bot.\n"
            "Please contact the administrator for access."
        )
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
        return ConversationHandler.END
    
    # Check if required files exist
    missing_files = [f for f in REQUIRED_FILES if not os.path.exists(f)]
    if missing_files:
        await update.message.reply_text(
            f"❌ Bot configuration error: Missing required files: {', '.join(missing_files)}. "
            "Please contact the administrator."
        )
        return ConversationHandler.END
    
    reply_keyboard = [['Color', 'Black', 'Both']]
    await update.message.reply_text(
        'Hi! I am the NID PDF to PNG Processor Bot.\n\n'
        'I can process a PDF for you using different methods. '
        'Please choose an option to start:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSING


async def choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the user's choice and asks for the PDF file."""
    # Check if user is authorized
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this bot."
        )
        return ConversationHandler.END
    
    user_choice = update.message.text.lower()
    context.user_data['choice'] = user_choice
    await update.message.reply_text(
        f'Excellent! You chose "{user_choice}".\nNow, please upload your PDF file.',
        reply_markup=ReplyKeyboardRemove(),
    )
    return PDF_UPLOAD


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the PDF file upload and processing."""
    # Check if user is authorized
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this bot."
        )
        return ConversationHandler.END
    
    if not update.message.document:
        await update.message.reply_text('It seems you sent something other than a document. Please upload a PDF file.')
        return PDF_UPLOAD

    if update.message.document.mime_type != 'application/pdf':
        await update.message.reply_text('⚠️ This is not a PDF file. Please send a correct PDF file only.')
        return PDF_UPLOAD
    
    # Check file size
    if update.message.document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f'⚠️ This file is too large. Maximum allowed size is {MAX_FILE_SIZE // (1024*1024)}MB.'
        )
        return PDF_UPLOAD

    doc = update.message.document
    file_id = doc.file_id
    # Sanitize file_id to prevent path traversal and include user ID for better tracking
    safe_file_id = f"{user_id}_{''.join(c for c in file_id if c.isalnum() or c in ('-', '_'))}"
    input_pdf_path = f'{safe_file_id}.pdf'
    
    try:
        # Download the user's PDF
        pdf_file = await context.bot.get_file(doc.file_id)
        await pdf_file.download_to_drive(input_pdf_path)
        await update.message.reply_text('✅ PDF received. Processing has started, this might take a moment...')

        user_choice = context.user_data.get('choice')
        output_files_to_send = []
        temp_files_to_clean = [input_pdf_path]

        # --- Run processing based on user's choice ---
        if user_choice in ['color', 'both']:
            logger.info(f"Running COLOR processing for user {user_id}, file {safe_file_id}")
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"NID_color_{safe_file_id}.png"
            final_output_path = f"NIDA4_color_{safe_file_id}.png"
            
            temp_files_to_clean.extend([merged_output_path, final_output_path])
            
            try:
                main_process_color(input_pdf_path, template_path, merged_output_path, a4_template_path, final_output_path)
                
                # Check for both output files and add them to the send list
                color_files_found = False
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                    color_files_found = True
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
                    color_files_found = True

                if not color_files_found:
                    await update.message.reply_text("Sorry, something went wrong during the 'color' processing.")
            except Exception as e:
                logger.error(f"Error in color processing for user {user_id}: {e}", exc_info=True)
                await update.message.reply_text("An error occurred during 'color' processing.")

        if user_choice in ['black', 'both']:
            logger.info(f"Running BLACK processing for user {user_id}, file {safe_file_id}")
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"NID_black_{safe_file_id}.png"
            final_output_path = f"NIDA4_black_{safe_file_id}.png"

            temp_files_to_clean.extend([merged_output_path, final_output_path])
            
            try:
                main_process_black(input_pdf_path, template_path, merged_output_path, a4_template_path, final_output_path)
                
                # Check for both output files and add them to the send list
                black_files_found = False
                if os.path.exists(merged_output_path):
                    output_files_to_send.append(merged_output_path)
                    black_files_found = True
                if os.path.exists(final_output_path):
                    output_files_to_send.append(final_output_path)
                    black_files_found = True

                if not black_files_found:
                    await update.message.reply_text("Sorry, something went wrong during the 'black' processing.")
            except Exception as e:
                logger.error(f"Error in black processing for user {user_id}: {e}", exc_info=True)
                await update.message.reply_text("An error occurred during 'black' processing.")

        # --- Send the final image(s) back to the user ---
        if output_files_to_send:
            await update.message.reply_text('Processing complete! Sending your file(s)...')
            for file_path in output_files_to_send:
                try:
                    with open(file_path, 'rb') as doc:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id, 
                            document=doc, 
                            filename=os.path.basename(file_path)
                        )
                except Exception as e:
                    logger.error(f"Error sending file {file_path} to user {user_id}: {e}")
                    await update.message.reply_text(f"Failed to send {os.path.basename(file_path)}.")
        else:
            await update.message.reply_text('Could not generate any output files. Please check the PDF and try again.')

    except Exception as e:
        logger.error(f"An error occurred for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text('A critical error occurred during processing. The operation has been stopped.')
    finally:
        # --- Cleanup all temporary files ---
        logger.info(f"Cleaning up temporary files for user {user_id}...")
        for temp_file in temp_files_to_clean:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.error(f"Error removing temporary file {temp_file} for user {user_id}: {e}")
        
        temp_img_dir = ".temp"
        if os.path.isdir(temp_img_dir):
            try:
                shutil.rmtree(temp_img_dir)
            except Exception as e:
                logger.error(f"Error removing temporary directory {temp_img_dir} for user {user_id}: {e}")

    await update.message.reply_text('All done! Use /start to process another file.')
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    # Check if user is authorized
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this bot."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        'Operation cancelled.', reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    """Run the bot."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found! Please add it to your .env file.")
        return

    # Create the Application
    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.Regex('^(Color|Black|Both)$'), choice)],
            PDF_UPLOAD: [MessageHandler(filters.Document.ALL, handle_pdf)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    # Start the Bot
    logger.info("Bot started and is polling for updates...")
    application.run_polling()


if __name__ == '__main__':
    main()