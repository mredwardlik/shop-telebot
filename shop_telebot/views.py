"""Views: text files with Telegram HTML and ``{placeholders}``.

A view is read on every use, so it can be edited while the bot is running.
Placeholders reach attributes of the objects passed to the view, for example
``{user.full_name}`` or ``{product.name}``. Values are HTML-escaped, so a user
named ``<b>`` can't break the markup or inject a link.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

NAMES = ('start', 'start_admin', 'menu', 'sent', 'sent_admin', 'no_product', 'no_command')

DEFAULTS = {
    'start': 'Добрый день! Выберите товар на клавиатуре внизу или откройте /menu.',
    'start_admin': 'Добрый день, админ! Сюда будут приходить заявки покупателей.',
    'menu': 'Каталог:',
    'sent': 'Спасибо! Наш оператор скоро с Вами свяжется.',
    'sent_admin': '<a href="tg://user?id={user.id}">{user.full_name}</a> хочет купить {product.name}.',
    'no_product': 'Такого товара нет. Выберите товар на клавиатуре или в /menu.',
    'no_command': 'Неизвестная команда. Есть /start и /menu.',
}


class Safe:
    """Wraps a value for ``str.format``: attributes and items are reachable,
    missing ones are empty, and the result is HTML-escaped.

    >>> class User: full_name = '<b>Eve</b>'; username = None
    >>> '{user.full_name} @{user.username}'.format(user=Safe(User()))
    '&lt;b&gt;Eve&lt;/b&gt; @'
    >>> '{p.names[1]} {p.count:>3}'.format(p=Safe({'names': ['a', 'b'], 'count': 2}))
    'b   2'
    """

    __slots__ = ('_value',)

    def __init__(self, value: Any):
        self._value = value

    def __getattr__(self, name: str) -> Safe:
        value = self._value
        if isinstance(value, dict):
            return Safe(value.get(name))
        return Safe(getattr(value, name, None))

    def __getitem__(self, key) -> Safe:
        try:
            return Safe(self._value[key])
        except (KeyError, IndexError, TypeError, ValueError):
            return Safe(None)

    def __format__(self, spec: str) -> str:
        if self._value is None:
            return ''
        try:
            text = format(self._value, spec)
        except (TypeError, ValueError):
            text = str(self._value)
        return html.escape(text)


class Views:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def path(self, name: str) -> Path:
        return self.directory / f'{name}.html'

    def source(self, name: str) -> str:
        try:
            return self.path(name).read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            log.warning('View "%s" not found, the default text is used', self.path(name))
            return DEFAULTS.get(name, '')

    def render(self, name: str, **context: Any) -> str:
        text = self.source(name)
        try:
            return text.format(**{key: Safe(value) for key, value in context.items()})
        except (KeyError, IndexError, ValueError) as error:
            log.error('View "%s" has a wrong placeholder (%s), it is sent as is', name, error)
            return text

    def missing(self) -> list[str]:
        return [name for name in NAMES if not self.path(name).is_file()]
