"""The bot: catalog on a keyboard, product cards with a buy button, orders to admins."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

from .catalog import Catalog, Product
from .settings import Settings
from .views import Views

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
COMMANDS = [
    types.BotCommand('start', 'Главное меню'),
    types.BotCommand('menu', 'Каталог товаров'),
]


class LogErrors(telebot.ExceptionHandler):
    """An error in one update is logged, the bot keeps working."""

    def handle(self, exception):
        log.error('Error while handling an update', exc_info=exception)
        return True


class ShopBot:
    def __init__(self, settings: Settings, *, threaded: bool = False):
        # Updates are handled one by one, so replies to a user come in order.
        self.settings = settings
        self.views = Views(settings.views_dir)
        self.catalog = Catalog(settings.products_dir)
        self.bot = telebot.TeleBot(settings.token, parse_mode='HTML', threaded=threaded,
                                   exception_handler=LogErrors())
        self._register()

    # helpers

    def is_admin(self, user: types.User) -> bool:
        return user is not None and user.id in self.settings.admins

    def product_context(self, product: Product | None) -> SimpleNamespace:
        """What ``{product...}`` means in views. ``current`` and ``descriptions``
        are kept for views written for the first version."""
        names = self.catalog.names
        return SimpleNamespace(
            name=product.name if product else None,
            current=product.name if product else None,
            description=product.description if product else None,
            index=names.index(product.name) if product and product.name in names else None,
            names=names,
            descriptions=[item.description for item in self.catalog],
            count=len(names),
        )

    def send(self, chat_id: int, text: str, **kwargs):
        """Send HTML; if Telegram can't parse it, log the error and send plain text."""
        if not text:
            return None
        try:
            return self.bot.send_message(chat_id, text, **kwargs)
        except ApiTelegramException as error:
            if "can't parse entities" not in str(error.description):
                raise
            log.error('Broken HTML in a message, sent as plain text: %s', error.description)
            return self.bot.send_message(chat_id, text, parse_mode='', **kwargs)

    def products_keyboard(self) -> types.ReplyKeyboardMarkup | types.ReplyKeyboardRemove:
        names = self.catalog.names
        if not names:
            return types.ReplyKeyboardRemove()
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=self.settings.row_width,
                                             input_field_placeholder='Выберите товар')
        keyboard.add(*(types.KeyboardButton(name) for name in names))
        return keyboard

    def buy_markup(self, product: Product) -> types.InlineKeyboardMarkup:
        return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(
            self.settings.buy_button, callback_data=f'buy:{product.id}'))

    def ordered_markup(self) -> types.InlineKeyboardMarkup:
        return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(
            self.settings.ordered_button, callback_data='noop'))

    def show_product(self, chat_id: int, product: Product, user: types.User):
        markup = None if self.is_admin(user) else self.buy_markup(product)
        if product.image is None:
            return self.send(chat_id, product.description, reply_markup=markup)

        with product.image.open('rb') as photo:
            if len(product.description) <= CAPTION_LIMIT:
                return self.bot.send_photo(chat_id, photo, caption=product.description, reply_markup=markup)
            self.bot.send_photo(chat_id, photo)
        return self.send(chat_id, product.description, reply_markup=markup)

    def notify_admins(self, text: str) -> int:
        delivered = 0
        for admin in sorted(self.settings.admins):
            try:
                self.bot.send_message(admin, text)
                delivered += 1
            except ApiTelegramException as error:
                log.warning("Can't send the order to admin %s: %s. The admin must start "
                            'the bot first.', admin, error.description)
        if not self.settings.admins:
            log.warning('An order came, but ADMINS is empty: %s', text)
        return delivered

    # handlers

    def _register(self):
        bot = self.bot

        @bot.message_handler(commands=['start'])
        def start(message: types.Message):
            view = 'start_admin' if self.is_admin(message.from_user) else 'start'
            text = self.views.render(view, message=message, user=message.from_user,
                                     product=self.product_context(None))
            self.send(message.chat.id, text, reply_markup=self.products_keyboard())

        @bot.message_handler(commands=['menu'])
        def menu(message: types.Message):
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(*(types.InlineKeyboardButton(product.name, callback_data=f'product:{product.id}')
                         for product in self.catalog))
            text = self.views.render('menu', message=message, user=message.from_user,
                                     product=self.product_context(None))
            if not len(self.catalog):
                text += '\n\nТоваров пока нет.'
            self.send(message.chat.id, text, reply_markup=markup)

        @bot.message_handler(content_types=['text'])
        def text(message: types.Message):
            product = self.catalog.get(message.text)
            if product is not None:
                return self.show_product(message.chat.id, product, message.from_user)
            view = 'no_command' if message.text.startswith('/') else 'no_product'
            reply = self.views.render(view, message=message, user=message.from_user,
                                      product=self.product_context(None))
            return self.send(message.chat.id, reply, reply_to_message_id=message.message_id,
                             reply_markup=self.products_keyboard())

        @bot.callback_query_handler(func=lambda call: True)
        def callback(call: types.CallbackQuery):
            kind, _, id_ = (call.data or '').partition(':')
            if kind not in ('product', 'buy'):
                return bot.answer_callback_query(call.id)

            product = self.catalog.by_id(id_)
            if product is None:
                return bot.answer_callback_query(call.id, 'Этого товара больше нет в каталоге',
                                                 show_alert=True)
            chat_id = call.message.chat.id if call.message else call.from_user.id

            if kind == 'product':
                bot.answer_callback_query(call.id)
                return self.show_product(chat_id, product, call.from_user)

            context = dict(call=call, message=call.message, user=call.from_user,
                           product=self.product_context(product))
            self.notify_admins(self.views.render('sent_admin', **context))
            log.info('Order: %s from user %s', product.name, call.from_user.id)
            bot.answer_callback_query(call.id, self.settings.ordered_button)
            if call.message:
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id,
                                                  reply_markup=self.ordered_markup())
                except ApiTelegramException as error:
                    log.debug("Can't mark the order button: %s", error.description)
            self.send(chat_id, self.views.render('sent', **context))

    # running

    def check(self) -> list[str]:
        """Problems with views and products, without connecting to Telegram."""
        problems = [f'view "{self.views.path(name)}" is missing, the default text is used'
                    for name in self.views.missing()]
        if not len(self.catalog):
            problems.append(f'no products in "{self.catalog.directory}"')
        for product in self.catalog:
            if len(product.description) > 4096:
                problems.append(f'"{product.name}" is longer than 4096 characters, Telegram will refuse it')
        return problems

    def run(self):
        me = self.bot.get_me()
        self.bot.set_my_commands(COMMANDS)
        log.info('@%s is running: %d products, %d admins. Stop with Ctrl+C.',
                 me.username, len(self.catalog), len(self.settings.admins))
        self.bot.infinity_polling()  # messages sent while the bot was off are answered too
