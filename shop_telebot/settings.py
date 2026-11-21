"""Settings from config.env, overridden by environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

KEYS = ('TOKEN', 'ADMINS', 'VIEWS_DIR', 'PRODUCTS_DIR', 'BUY_BUTTON', 'ORDERED_BUTTON', 'ROW_WIDTH')
TOKEN_PATTERN = re.compile(r'^\d+:[\w-]{30,}$')


class ConfigError(Exception):
    """The configuration is missing or wrong."""


@dataclass(frozen=True)
class Settings:
    token: str
    admins: frozenset[int] = field(default_factory=frozenset)
    views_dir: Path = Path('views')
    products_dir: Path = Path('views/products')
    buy_button: str = '🛒 Купить'
    ordered_button: str = '✅ Заявка отправлена'
    row_width: int = 2


def parse_admins(value: str) -> frozenset[int]:
    """Telegram ids separated by commas or spaces.

    >>> sorted(parse_admins('123, 456 789,'))
    [123, 456, 789]
    """
    ids = [part for part in re.split(r'[\s,;]+', value or '') if part]
    try:
        return frozenset(int(part) for part in ids)
    except ValueError:
        raise ConfigError(f'ADMINS must be Telegram user ids separated by commas, not "{value}". '
                          'Your id can be found with @userinfobot.') from None


def load_settings(path: str | os.PathLike = 'config.env',
                  environ: Mapping[str, str] | None = None) -> Settings:
    """Read the settings. Paths in the file are relative to the file itself.

    Every key can also be set as an environment variable, which is handy on a
    server: ``TOKEN=... python -m shop_telebot``.
    """
    environ = os.environ if environ is None else environ
    path = Path(path)
    values: dict[str, str | None] = dict(dotenv_values(path)) if path.is_file() else {}
    values.update({key: environ[key] for key in KEYS if environ.get(key)})

    if not values:
        raise ConfigError(f'"{path}" not found. Copy config.example.env to config.env '
                          'and put the token of your bot there.')

    token = (values.get('TOKEN') or '').strip()
    if not TOKEN_PATTERN.match(token):
        raise ConfigError(f'TOKEN in "{path}" is not set. Get a token from @BotFather, '
                          'it looks like 123456789:AAH...')

    base = path.resolve().parent
    views_dir = base / (values.get('VIEWS_DIR') or 'views')
    products_dir = base / (values.get('PRODUCTS_DIR') or 'views/products')

    try:
        row_width = int(values.get('ROW_WIDTH') or 2)
    except ValueError:
        raise ConfigError('ROW_WIDTH must be a number of buttons in a row.') from None

    defaults = Settings(token='')
    return Settings(
        token=token,
        admins=parse_admins(values.get('ADMINS') or ''),
        views_dir=views_dir,
        products_dir=products_dir,
        buy_button=(values.get('BUY_BUTTON') or defaults.buy_button).strip(),
        ordered_button=(values.get('ORDERED_BUTTON') or defaults.ordered_button).strip(),
        row_width=max(1, min(row_width, 8)),
    )
