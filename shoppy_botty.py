import logging
import time
from os import getenv

import messages
import mysql.connector
import schedule
from dotenv import load_dotenv
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# load environment variables
load_dotenv()

# init bot
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
updater = Updater(token=getenv("API_KEY"))
dispatcher = updater.dispatcher

# init mysql
connection = mysql.connector.connect(
    host=getenv("DB_HOST"),
    user=getenv("DB_USER"),
    passwd=getenv("DB_PASSWD"),
    database=getenv("DB_DATABASE")
)
cursor = connection.cursor()

# messages
messages.init(connection)
message_start = messages.get_message("cmd_start")
message_help = messages.get_message("cmd_help")
message_menu = messages.get_message("cmd_menu").replace("$menu_products", messages.get_menu_products())
message_products = messages.get_message("cmd_products")
message_products_weights = messages.get_message("cmd_products_weights")
message_products_added = messages.get_message("cmd_products_added")
message_cart = messages.get_message("cmd_cart")
message_cart_empty = messages.get_message("cmd_cart_empty")
message_chat_cache_cleared = messages.get_message("chat_cache_cleared")

# link to messages-dicts
products = messages.products
settings = messages.settings

# chat-cache
carts = {}
last_interacted = {}
cache_time = float(settings["chat_cache_time"]) * 60  # cache time in seconds


def cleanup():
    global last_interacted
    clear_count = 0
    new_last_interacted = last_interacted.copy()
    for cur_chat in last_interacted.items():
        chat_id = cur_chat[0]
        last_timestamp = cur_chat[1]
        if time.time() - last_timestamp >= cache_time:
            clear_count += 1
            if chat_id in carts:
                carts.pop(chat_id)
            new_last_interacted.pop(chat_id)
            dispatcher.bot.send_message(chat_id=chat_id, text=message_chat_cache_cleared)
    last_interacted = new_last_interacted
    if clear_count > 0:
        print(f"cleared cache of {clear_count} users due to inactivity")


schedule.every(cache_time / 2).seconds.do(cleanup)


# command functions
def start_handler_function(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(text=message_start)


def help_handler_function(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(text=message_help)


def menu_handler_function(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(text=message_menu)


def products_handler_function(update: Update, context: CallbackContext) -> None:
    reply_markup = InlineKeyboardMarkup(messages.get_products_keyboard())
    update.message.reply_text(message_products, reply_markup=reply_markup)


def cart_handler_function(update: Update, context: CallbackContext) -> None:
    cart_handler_function_implementation(update, context, False)


def cart_handler_function_implementation(update: Update, context: CallbackContext, edit: bool) -> None:
    chat_id = update.effective_chat.id
    msg = None
    reply_markup = None
    if chat_id not in carts:
        msg = message_cart_empty
    else:
        msg = message_cart
        reply_markup = InlineKeyboardMarkup(messages.get_cart_keyboard(carts[chat_id]))
    if edit:
        update.callback_query.edit_message_text(text=msg, reply_markup=reply_markup)
    else:
        update.message.reply_text(text=msg, reply_markup=reply_markup)


def finish_handler_function(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in carts:
        update.effective_chat.send_message(text=messages.get_finish_message(carts[chat_id]))
        carts.pop(chat_id)
    else:
        cart_handler_function(update, context)


def button_handler_function(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()
    msg = None
    reply_markup = None
    task_id = query.data[0:2]
    data = query.data[2:]
    # products
    # >select product
    if task_id == "01":
        product_id = int(data)
        msg = message_products_weights.replace("$name", products[product_id][0])
        reply_markup = InlineKeyboardMarkup(messages.get_products_weights_keyboard(product_id))
        last_interacted[chat_id] = time.time()
    # >select weight
    elif task_id == "02":
        product_id = int(data.split("$$$")[0])
        weight = data.split("$$$")[1]
        if chat_id not in carts:
            carts[chat_id] = {}
        if product_id not in carts[chat_id]:
            carts[chat_id][product_id] = {}
        if weight not in carts[chat_id][product_id]:
            carts[chat_id][product_id][weight] = 1
        else:
            carts[chat_id][product_id][weight] += 1
        last_interacted[chat_id] = time.time()
        msg = message_products_added.replace("$weight", weight).replace("$name", products[product_id][0])
    # >back
    elif task_id == "03":
        last_interacted.pop(chat_id)
        msg = message_products
        reply_markup = InlineKeyboardMarkup(messages.get_products_keyboard())
    # >info
    elif task_id == "04":
        product_id = int(data)
        msg = messages.get_message("products_product").replace("$name", products[product_id][0]) \
            .replace("$description", products[product_id][1])
        reply_markup = InlineKeyboardMarkup(messages.get_weights_keyboard(product_id))
        update.effective_chat.send_photo(open(products[product_id][2], "rb"))

    # cart
    # >remove
    elif task_id == "11" and chat_id in carts:
        product_id = int(data.split("$$$")[0])
        weight = data.split("$$$")[1]
        if chat_id in carts and product_id in carts[chat_id] and weight in carts[chat_id][product_id]:
            carts[chat_id][product_id].pop(weight)
            if len(carts[chat_id][product_id]) == 0:
                carts[chat_id].pop(product_id)
            if len(carts[chat_id]) == 0:
                carts.pop(chat_id)
        cart_handler_function_implementation(update, context, True)
    # >decrease
    elif task_id == "12" and chat_id in carts:
        product_id = int(data.split("$$$")[0])
        weight = data.split("$$$")[1]
        carts[chat_id][product_id][weight] -= 1
        if chat_id in carts and product_id in carts[chat_id] and weight in carts[chat_id][product_id]:
            if carts[chat_id][product_id][weight] == 0:
                carts[chat_id][product_id].pop(weight)
            if len(carts[chat_id][product_id]) == 0:
                carts[chat_id].pop(product_id)
            if len(carts[chat_id]) == 0:
                carts.pop(chat_id)
        cart_handler_function_implementation(update, context, True)
    # >increase
    elif task_id == "13" and chat_id in carts:
        product_id = int(data.split("$$$")[0])
        weight = data.split("$$$")[1]
        if chat_id in carts and product_id in carts[chat_id] and weight in carts[chat_id][product_id]:
            carts[chat_id][product_id][weight] += 1
        cart_handler_function_implementation(update, context, True)
    elif task_id == "14" and chat_id in carts:
        finish_handler_function(update, context)

    if msg is not None:
        query.edit_message_text(text=msg, reply_markup=reply_markup)


# register handlers
start_handler = CommandHandler('start', start_handler_function)
help_handler = CommandHandler('help', help_handler_function)
menu_handler = CommandHandler('menu', menu_handler_function)
products_handler = CommandHandler('products', products_handler_function)
cart_handler = CommandHandler('cart', cart_handler_function)
finish_handler = CommandHandler('finish', finish_handler_function)
dispatcher.add_handler(start_handler)
dispatcher.add_handler(help_handler)
dispatcher.add_handler(menu_handler)
dispatcher.add_handler(products_handler)
dispatcher.add_handler(cart_handler)
dispatcher.add_handler(finish_handler)
dispatcher.add_handler(CallbackQueryHandler(button_handler_function))
updater.start_polling()

# schedule tasks
while 1:
    schedule.run_pending()
    time.sleep(1)
