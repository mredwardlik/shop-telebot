from conftest import ADMIN, USER, keyboard, press, send_text

from shop_telebot.catalog import product_id


def test_start_shows_products_keyboard(shop, telegram):
    send_text(shop, '/start')
    reply = telegram.last(USER)
    assert 'Анна' in reply['text'] and '/menu' in reply['text']
    rows = keyboard(reply)['keyboard']
    assert [button['text'] for row in rows for button in row] == ['Брюки', 'Рубашки']
    assert keyboard(reply)['resize_keyboard'] is True


def test_start_for_admin(shop, telegram):
    send_text(shop, '/start', user_id=ADMIN)
    assert 'админ' in telegram.last(ADMIN)['text']


def test_product_by_keyboard(shop, telegram):
    send_text(shop, 'Брюки')
    reply = telegram.last(USER)
    assert reply['text'].startswith('<b>Брюки</b>')
    [[button]] = keyboard(reply)['inline_keyboard']
    assert button == {'text': '🛒 Купить', 'callback_data': f'buy:{product_id("Брюки")}'}


def test_product_name_is_case_insensitive(shop, telegram):
    send_text(shop, '  рубашки ')
    assert telegram.last(USER)['text'].startswith('<b>Рубашка</b>')


def test_admin_has_no_buy_button(shop, telegram):
    send_text(shop, 'Брюки', user_id=ADMIN)
    assert 'reply_markup' not in telegram.last(ADMIN)


def test_menu_and_product_button(shop, telegram):
    send_text(shop, '/menu')
    buttons = keyboard(telegram.last(USER))['inline_keyboard']
    assert [row[0]['text'] for row in buttons] == ['Брюки', 'Рубашки']

    press(shop, buttons[1][0]['callback_data'])
    assert telegram.last(USER)['text'].startswith('<b>Рубашка</b>')
    assert len(telegram.calls('answerCallbackQuery')) == 1


def test_buy(shop, telegram):
    press(shop, f'buy:{product_id("Брюки")}', message_id=77)

    order = telegram.last(ADMIN)['text']
    assert 'Новая заявка' in order and 'Брюки' in order
    assert '<a href="tg://user?id=2000">Анна Смирнова</a>' in order

    assert 'Брюки' in telegram.last(USER)['text'] and 'оператор' in telegram.last(USER)['text']
    [answer] = telegram.calls('answerCallbackQuery')
    assert answer['text'] == '✅ Заявка отправлена'
    [edit] = telegram.calls('editMessageReplyMarkup')
    assert int(edit['message_id']) == 77
    assert keyboard(edit)['inline_keyboard'][0][0]['text'] == '✅ Заявка отправлена'


def test_user_name_is_escaped_in_order(shop, telegram):
    press(shop, f'buy:{product_id("Брюки")}', first_name='<a href="evil">Eve', last_name=None)
    order = telegram.last(ADMIN)['text']
    assert '&lt;a href=&quot;evil&quot;&gt;Eve' in order and 'href="evil"' not in order


def test_order_reaches_other_admins_if_one_fails(make_shop, telegram):
    shop = make_shop(admins=frozenset({ADMIN, 3000}))
    telegram.errors[('sendMessage', ADMIN)] = (403, 'Forbidden: bot was blocked by the user')
    press(shop, f'buy:{product_id("Брюки")}')
    assert telegram.sent(3000) and 'Новая заявка' in telegram.last(3000)['text']
    assert 'оператор' in telegram.last(USER)['text']


def test_order_without_admins(make_shop, telegram, caplog):
    shop = make_shop(admins=frozenset())
    press(shop, f'buy:{product_id("Брюки")}')
    assert 'оператор' in telegram.last(USER)['text']
    assert 'ADMINS is empty' in caplog.text


def test_removed_product(shop, telegram, shop_dir):
    (shop_dir / 'views' / 'products' / 'Брюки.html').unlink()
    press(shop, f'buy:{product_id("Брюки")}')
    [answer] = telegram.calls('answerCallbackQuery')
    assert 'больше нет' in answer['text'] and answer['show_alert'] is True
    assert not telegram.sent(ADMIN)


def test_unknown_callback_is_answered(shop, telegram):
    press(shop, 'noop')
    press(shop, 'something:else')
    assert len(telegram.calls('answerCallbackQuery')) == 2
    assert not telegram.sent()


def test_unknown_text_and_command(shop, telegram):
    send_text(shop, 'Шапки')
    assert 'не существует' in telegram.last(USER)['text']
    send_text(shop, '/help')
    assert 'Неизвестная команда' in telegram.last(USER)['text']


def test_products_are_reloaded(shop, telegram, shop_dir):
    products = shop_dir / 'views' / 'products'
    (products / '0 Футболки.html').write_text('<b>Футболки</b> из хлопка', encoding='utf-8')
    send_text(shop, '/start')
    rows = keyboard(telegram.last(USER))['keyboard']
    assert [button['text'] for row in rows for button in row] == ['Футболки', 'Брюки', 'Рубашки']
    send_text(shop, 'Футболки')
    assert telegram.last(USER)['text'] == '<b>Футболки</b> из хлопка'


def test_product_with_photo(shop, telegram, shop_dir):
    (shop_dir / 'views' / 'products' / 'Брюки.jpg').write_bytes(b'\xff\xd8\xff fake jpeg')
    send_text(shop, 'Брюки')
    [photo] = telegram.calls('sendPhoto')
    assert photo['caption'].startswith('<b>Брюки</b>')
    assert 'buy:' in photo['reply_markup']


def test_long_description_with_photo(shop, telegram, shop_dir):
    products = shop_dir / 'views' / 'products'
    (products / 'Пальто.html').write_text('Пальто ' * 200, encoding='utf-8')
    (products / 'Пальто.png').write_bytes(b'\x89PNG fake')
    send_text(shop, 'Пальто')
    [photo] = telegram.calls('sendPhoto')
    assert 'caption' not in photo
    assert telegram.last(USER)['text'].startswith('Пальто Пальто')
    assert 'buy:' in telegram.last(USER)['reply_markup']


def test_broken_html_is_sent_as_plain_text(shop, telegram, shop_dir, caplog):
    (shop_dir / 'views' / 'products' / 'Брюки.html').write_text('<b>Брюки', encoding='utf-8')
    telegram.errors[('sendMessage', None)] = (
        400, lambda params: "Bad Request: can't parse entities" if params.get('parse_mode') else None)
    send_text(shop, 'Брюки')
    first, second = telegram.calls('sendMessage')
    assert first['parse_mode'] == 'HTML' and 'parse_mode' not in second
    assert 'Broken HTML' in caplog.text


def test_empty_catalog(make_shop, telegram, tmp_path):
    shop = make_shop(products_dir=tmp_path / 'nothing')
    send_text(shop, '/start')
    assert keyboard(telegram.last(USER)) == {'remove_keyboard': True}
    send_text(shop, '/menu')
    assert 'Товаров пока нет' in telegram.last(USER)['text']


def test_error_in_handler_doesnt_stop_the_bot(shop, telegram, caplog):
    telegram.errors[('sendMessage', None)] = (500, 'Internal Server Error')
    send_text(shop, '/start')
    assert 'Error while handling an update' in caplog.text
    telegram.errors.clear()
    send_text(shop, '/start')
    assert 'Анна' in telegram.last(USER)['text']


def test_run_sets_commands(shop, telegram, monkeypatch):
    monkeypatch.setattr(shop.bot, 'infinity_polling', lambda **kwargs: None)
    shop.run()
    [commands] = telegram.calls('setMyCommands')
    assert '"start"' in commands['commands'] and '"menu"' in commands['commands']
