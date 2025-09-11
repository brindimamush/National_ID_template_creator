import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
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


def start(update: Update, context: CallbackContext) -> int:
    """Starts the conversation and asks for user's choice."""
    reply_keyboard = [['Color', 'Black', 'Both']]
    update.message.reply_text(
        'Hi! I am the Flipped PDF Processor Bot.\n\n'
        'I can process a PDF for you using different methods. '
        'Please choose an option to start:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSING


def choice(update: Update, context: CallbackContext) -> int:
    """Stores the user's choice and asks for the PDF file."""
    user_choice = update.message.text.lower()
    context.user_data['choice'] = user_choice
    update.message.reply_text(
        f'Excellent! You chose "{user_choice}".\nNow, please upload your PDF file.',
        reply_markup=ReplyKeyboardRemove(),
    )
    return PDF_UPLOAD


def handle_pdf(update: Update, context: CallbackContext) -> int:
    """Handles the PDF file upload and processing."""
    if not update.message.document:
        update.message.reply_text('It seems you sent something other than a document. Please upload a PDF file.')
        return PDF_UPLOAD

    if update.message.document.mime_type != 'application/pdf':
        update.message.reply_text('⚠️ This is not a PDF file. Please send a correct PDF file only.')
        return PDF_UPLOAD

    doc = update.message.document
    file_id = doc.file_id
    input_pdf_path = f'{file_id}.pdf'
    
    try:
        # Download the user's PDF
        pdf_file = context.bot.get_file(doc.file_id)
        pdf_file.download(input_pdf_path)
        update.message.reply_text('✅ PDF received. Processing has started, this might take a moment...')

        user_choice = context.user_data.get('choice')
        output_files_to_send = []
        temp_files_to_clean = []

        # --- Run processing based on user's choice ---
        if user_choice in ['color', 'both']:
            logger.info(f"Running COLOR processing for {file_id}")
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"merged_color_{file_id}.png"
            final_output_path = f"final_color_{file_id}.png"
            
            temp_files_to_clean.extend([merged_output_path, final_output_path])
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
                 update.message.reply_text("Sorry, something went wrong during the 'color' processing.")


        if user_choice in ['black', 'both']:
            logger.info(f"Running BLACK processing for {file_id}")
            template_path = "template_final.png"
            a4_template_path = "a4.png"
            merged_output_path = f"merged_black_{file_id}.png"
            final_output_path = f"final_black_{file_id}.png"

            temp_files_to_clean.extend([merged_output_path, final_output_path])
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
                update.message.reply_text("Sorry, something went wrong during the 'black' processing.")


        # --- Send the final image(s) back to the user ---
        if output_files_to_send:
            update.message.reply_text('Processing complete! Sending your file(s)...')
            for file_path in output_files_to_send:
                with open(file_path, 'rb') as doc:
                    context.bot.send_document(chat_id=update.effective_chat.id, document=doc, filename=os.path.basename(file_path))
        else:
            update.message.reply_text('Could not generate any output files. Please check the PDF and try again.')

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        update.message.reply_text('A critical error occurred during processing. The operation has been stopped.')
    finally:
        # --- Cleanup all temporary files ---
        logger.info("Cleaning up temporary files...")
        if os.path.exists(input_pdf_path):
            os.remove(input_pdf_path)
        for temp_file in temp_files_to_clean:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        temp_img_dir = ".temp"
        if os.path.isdir(temp_img_dir):
            for item in os.listdir(temp_img_dir):
                os.remove(os.path.join(temp_img_dir, item))
            os.rmdir(temp_img_dir)


    update.message.reply_text('All done! Use /start to process another file.')
    context.user_data.clear()
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    update.message.reply_text(
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

    updater = Updater(token)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(Filters.regex('^(Color|Black|Both)$'), choice)],
            PDF_UPLOAD: [MessageHandler(Filters.document, handle_pdf)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(conv_handler)

    updater.start_polling()
    logger.info("Bot started and is polling for updates...")
    updater.idle()


if __name__ == '__main__':
    main()

