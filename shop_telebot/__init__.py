"""A small Telegram shop: products from HTML files, orders go to admins."""

__version__ = '1.0.0'

from .bot import ShopBot
from .catalog import Catalog, Product
from .settings import ConfigError, Settings, load_settings
from .views import Views

__all__ = ['ShopBot', 'Catalog', 'Product', 'ConfigError', 'Settings', 'load_settings', 'Views']
