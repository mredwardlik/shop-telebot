"""``python -m shop_telebot [--config config.env] [--check]``"""

from __future__ import annotations

import argparse
import logging
import sys

from telebot.apihelper import ApiTelegramException

from . import __version__
from .bot import ShopBot
from .settings import ConfigError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m shop_telebot',
                                     description='Run the Telegram shop bot.')
    parser.add_argument('-c', '--config', default='config.env', help='settings file (default: config.env)')
    parser.add_argument('--check', action='store_true',
                        help='check the settings, views and products, and exit')
    parser.add_argument('-v', '--verbose', action='store_true', help='log every request')
    parser.add_argument('-V', '--version', action='version', version=f'shop-telebot {__version__}')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)-7s %(message)s', datefmt='%H:%M:%S')
    log = logging.getLogger('shop_telebot')

    try:
        settings = load_settings(args.config)
    except ConfigError as error:
        log.error('%s', error)
        return 2

    shop = ShopBot(settings)
    problems = shop.check()
    for problem in problems:
        log.warning('%s', problem)
    if not settings.admins:
        log.warning('ADMINS is empty: nobody will receive orders')
    if args.check:
        names = ', '.join(shop.catalog.names) or 'none'
        print(f'Products ({len(shop.catalog)}): {names}')
        print(f'Admins: {len(settings.admins)}')
        print('OK' if not problems else f'{len(problems)} problem(s), see above')
        return 0 if not problems else 1

    try:
        shop.run()
    except ApiTelegramException as error:
        if error.error_code == 401:
            log.error('Telegram doesn\'t accept the token. Check TOKEN in "%s".', args.config)
            return 2
        raise
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
