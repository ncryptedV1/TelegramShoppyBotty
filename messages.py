from telegram import InlineKeyboardButton, KeyboardButton

connection = None
products: dict = None
prices: dict = None
messages: dict = None
settings: dict = None


def init(db_connection) -> None:
    global connection, products, prices, messages, settings
    connection = db_connection
    cursor = connection.cursor()

    statement = "SELECT * FROM products ORDER BY name"
    cursor.execute(statement)
    products = cursor.fetchall()
    # convert to dict to access individual products quicker via id
    products_dict = {}
    for product in products:
        products_dict[product[0]] = product[1:]
    products = products_dict

    statement = "SELECT product_id,weight,unit,price FROM prices LEFT JOIN weights w ON w.id=weight_id ORDER BY product_id, weight, unit"
    cursor.execute(statement)
    prices = cursor.fetchall()
    # convert to dict to access individual prices quicker via product_id & weight
    prices_dict = {}
    for price_tuple in prices:
        product_id = price_tuple[0]
        weight = str(price_tuple[1])+price_tuple[2]
        price = price_tuple[3]
        if not product_id in prices_dict:
            prices_dict[product_id] = {}
        prices_dict[product_id][weight] = round(price, 2)
    prices = prices_dict

    statement = "SELECT name,content FROM messages"
    cursor.execute(statement)
    messages = cursor.fetchall()
    # convert to dict to access individual messages quicker via id
    messages_dict = {}
    for message in messages:
        messages_dict[message[0]] = message[1]
    messages = messages_dict

    statement = "SELECT name,content FROM settings"
    cursor.execute(statement)
    settings = cursor.fetchall()
    # convert to dict to access individual messages quicker via id
    settings_dict = {}
    for setting in settings:
        settings_dict[setting[0]] = setting[1]
    settings = settings_dict


# Menu
def get_menu_product_prices(product_id: int) -> str:
    price_template = messages["menu_price"]
    msg = ""
    for price in prices[product_id].items():
        msg += price_template \
                   .replace("$weight", price[0]) \
                   .replace("$price", to_user_price(price[1])) + "\n"
    msg = msg[:-1]
    return msg


def get_menu_product(product_id: int) -> str:
    product_template = messages["menu_product"]
    infos = products[product_id]
    return product_template.replace("$name", infos[0]) \
        .replace("$description", infos[1]) \
        .replace("$prices", get_menu_product_prices(product_id))


def get_menu_products() -> str:
    msg = ""
    for product_id in products.keys():
        msg += get_menu_product(product_id) + "\n\n"
    msg = msg[:-2]
    return msg


# General
def get_message(message_id: str) -> str:
    return messages[message_id]


# Keyboards
def get_products_keyboard():
    keyboard = []
    for product in products.items():
        keyboard.append([InlineKeyboardButton(product[1][0], callback_data=f"01{product[0]}")])
    return keyboard


def get_products_weights_keyboard(product_id: int):
    keyboard = [[InlineKeyboardButton(get_message("cmd_products_back"), callback_data="03")],
                [InlineKeyboardButton(get_message("cmd_products_info"), callback_data=f"04{product_id}")]]
    keyboard.extend(get_weights_keyboard(product_id))
    return keyboard


def get_weights_keyboard(product_id: int):
    price_template = messages["menu_price"]
    keyboard = []
    for price in prices[product_id].items():
        keyboard.append([InlineKeyboardButton(price_template.
                                              replace("$weight", price[0]).
                                              replace("$price", to_user_price(price[1])),
                                              callback_data=f"02{product_id}$$${price[0]}")])
    return keyboard


def get_cart_keyboard(cart: dict):
    keyboard = []
    for product_pair in cart.items():
        product_id = product_pair[0]
        for weight_pair in product_pair[1].items():
            weight = weight_pair[0]
            amount = weight_pair[1]
            keyboard.append([InlineKeyboardButton(text=f"{products[product_id][0]} - {weight}", callback_data="none"),
                             InlineKeyboardButton(text="X", callback_data=f"11{product_id}$$${weight}")])
            keyboard.append([InlineKeyboardButton(text="-", callback_data=f"12{product_id}$$${weight}"),
                             InlineKeyboardButton(text=f"{amount}", callback_data="none"),
                             InlineKeyboardButton(text="+", callback_data=f"13{product_id}$$${weight}")])
    keyboard.append([InlineKeyboardButton(text=get_message("cmd_cart_checkout"), callback_data="14")])
    return keyboard


def get_finish_message(cart: dict) -> str:
    finish_message = get_message("cmd_finish")
    invoice_products = ""
    invoice_product_template = get_message("invoice_product")
    total = 0
    for product_pair in cart.items():
        product_id = product_pair[0]
        for weight_pair in product_pair[1].items():
            weight = weight_pair[0]
            amount = weight_pair[1]
            cur_price = amount * prices[product_id][weight]
            invoice_products += invoice_product_template.replace("$name", products[product_id][0]) \
                                    .replace("$weight", weight) \
                                    .replace("$amount", f"{amount}") \
                                    .replace("$single_price", f"{prices[product_id][weight]}") \
                                    .replace("$price", to_user_price(cur_price)) + "\n"
            total += cur_price
    invoice_products = invoice_products[:-1]
    return finish_message.replace("$invoice_products", invoice_products).replace("$total", to_user_price(total))


# formatter
def to_user_price(price: float) -> str:
    price = round(price, 2)
    return f"{str(price).replace('.', ',')} {settings['currency_symbol']}"
