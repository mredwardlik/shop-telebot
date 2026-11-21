"""A fake Telegram API: requests of the bot are recorded, updates are fed by hand."""

from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest
from telebot import apihelper, types

from shop_telebot import ShopBot, Settings

ROOT = Path(__file__).resolve().parent.parent
TOKEN = '123456789:' + 'A' * 35
ADMIN = 1000
USER = 2000


class Response:
    def __init__(self, payload: dict, status: int = 200):
        self.payload, self.status_code = payload, status
        self.text = json.dumps(payload)
        self.reason = 'OK'

    def json(self):
        return self.payload


class FakeTelegram:
    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        self.errors: dict[tuple[str, int | None], tuple[int, str]] = {}
        self._ids = itertools.count(100)

    def __call__(self, method, url, params=None, files=None, **kwargs):
        name = url.rsplit('/', 1)[-1]
        params = dict(params or {})
        if files:
            params['files'] = {key: getattr(value, 'name', value) for key, value in files.items()}
        self.requests.append((name, params))

        chat = params.get('chat_id')
        chat = int(chat) if chat is not None else None
        error = self.errors.get((name, chat)) or self.errors.get((name, None))
        if error:
            code, description = error
            if callable(description):
                description = description(params)
            if description:
                return Response({'ok': False, 'error_code': code, 'description': description}, code)

        if name in ('sendMessage', 'sendPhoto', 'editMessageReplyMarkup'):
            return Response({'ok': True, 'result': {
                'message_id': next(self._ids), 'date': 0,
                'chat': {'id': chat or USER, 'type': 'private'},
                'text': params.get('text', ''),
            }})
        if name == 'getMe':
            return Response({'ok': True, 'result': {'id': 1, 'is_bot': True, 'first_name': 'Shop',
                                                    'username': 'test_shop_bot'}})
        return Response({'ok': True, 'result': True})

    def calls(self, name: str) -> list[dict]:
        return [params for method, params in self.requests if method == name]

    def sent(self, chat_id: int | None = None) -> list[dict]:
        return [params for method, params in self.requests if method in ('sendMessage', 'sendPhoto')
                and (chat_id is None or int(params['chat_id']) == chat_id)]

    def last(self, chat_id: int | None = None) -> dict:
        return self.sent(chat_id)[-1]

    def clear(self):
        self.requests.clear()


def keyboard(params: dict) -> dict:
    return json.loads(params['reply_markup'])


@pytest.fixture
def telegram(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(apihelper, 'CUSTOM_REQUEST_SENDER', fake)
    return fake


@pytest.fixture
def shop_dir(tmp_path):
    """A copy of the views and products of the repository."""
    shutil.copytree(ROOT / 'views', tmp_path / 'views')
    return tmp_path


@pytest.fixture
def make_shop(telegram, shop_dir):
    def make(**overrides) -> ShopBot:
        options = dict(token=TOKEN, admins=frozenset({ADMIN}), views_dir=shop_dir / 'views',
                       products_dir=shop_dir / 'views' / 'products')
        options.update(overrides)
        return ShopBot(Settings(**options), threaded=False)
    return make


@pytest.fixture
def shop(make_shop) -> ShopBot:
    return make_shop()


_update_ids = itertools.count(1)


def user_json(user_id: int, first_name: str = 'Анна', last_name: str | None = 'Смирнова',
              username: str | None = 'anna') -> dict:
    data = {'id': user_id, 'is_bot': False, 'first_name': first_name}
    if last_name:
        data['last_name'] = last_name
    if username:
        data['username'] = username
    return data


def message_json(text: str, user_id: int = USER, **user) -> dict:
    data = {'message_id': next(_update_ids), 'date': 0, 'text': text,
            'chat': {'id': user_id, 'type': 'private'}, 'from': user_json(user_id, **user)}
    if text.startswith('/'):
        command = text.split()[0]
        data['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': len(command)}]
    return data


def send_text(shop: ShopBot, text: str, user_id: int = USER, **user):
    update = types.Update.de_json({'update_id': next(_update_ids),
                                   'message': message_json(text, user_id, **user)})
    shop.bot.process_new_updates([update])


def press(shop: ShopBot, data: str, user_id: int = USER, message_id: int = 55, **user):
    update = types.Update.de_json({'update_id': next(_update_ids), 'callback_query': {
        'id': str(next(_update_ids)), 'chat_instance': '1', 'data': data,
        'from': user_json(user_id, **user),
        'message': {'message_id': message_id, 'date': 0, 'text': '...',
                    'chat': {'id': user_id, 'type': 'private'}},
    }})
    shop.bot.process_new_updates([update])
