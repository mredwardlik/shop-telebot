"""Products: one ``<name>.html`` file each, and optionally a photo with the same name.

::

    products/
    ├── 1 Рубашки.html     # the number only sets the order, it isn't shown
    ├── 1 Рубашки.jpg      # sent as a photo with the description as caption
    └── 2 Брюки.html

The folder is read again when something in it changes, so products can be
added, edited and removed while the bot is running.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
_ORDER_PREFIX = re.compile(r'^\d+[\s._)-]+')


def product_id(name: str) -> str:
    """Short id for button data: stable while the name is the same."""
    return hashlib.sha1(name.encode('utf-8')).hexdigest()[:10]


def display_name(stem: str) -> str:
    """
    >>> display_name('01 Рубашки'), display_name('2_Брюки'), display_name('Брюки')
    ('Рубашки', 'Брюки', 'Брюки')
    >>> display_name('2024')
    '2024'
    """
    name = _ORDER_PREFIX.sub('', stem, count=1).strip()
    return name or stem


@dataclass(frozen=True)
class Product:
    name: str
    description: str
    image: Path | None = None

    @property
    def id(self) -> str:
        return product_id(self.name)


class Catalog:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._stamp: tuple | None = None
        self._products: list[Product] = []

    def _snapshot(self) -> tuple:
        try:
            return tuple(sorted((entry.name, entry.stat().st_mtime_ns, entry.stat().st_size)
                                for entry in self.directory.iterdir() if entry.is_file()))
        except FileNotFoundError:
            return ()

    def _load(self) -> list[Product]:
        if not self.directory.is_dir():
            log.warning('Products folder "%s" not found', self.directory)
            return []
        files = sorted(self.directory.iterdir(), key=lambda path: path.name.casefold())
        images = {path.stem: path for path in files if path.suffix.lower() in IMAGE_EXTENSIONS}

        products, seen = [], set()
        for path in files:
            if path.suffix.lower() != '.html' or not path.is_file():
                continue
            name = display_name(path.stem)
            if name.casefold() in seen:
                log.warning('Product "%s" is defined twice, "%s" is skipped', name, path.name)
                continue
            seen.add(name.casefold())
            description = path.read_text(encoding='utf-8').strip()
            products.append(Product(name, description, images.get(path.stem)))
        log.info('Loaded %d products from "%s"', len(products), self.directory)
        return products

    @property
    def products(self) -> list[Product]:
        stamp = self._snapshot()
        if stamp != self._stamp:
            self._products, self._stamp = self._load(), stamp
        return self._products

    @property
    def names(self) -> list[str]:
        return [product.name for product in self.products]

    def get(self, name: str) -> Product | None:
        """Product by name, case-insensitive."""
        key = name.strip().casefold()
        return next((product for product in self.products if product.name.casefold() == key), None)

    def by_id(self, id_: str) -> Product | None:
        return next((product for product in self.products if product.id == id_), None)

    def index(self, product: Product) -> int:
        return self.names.index(product.name)

    def __len__(self) -> int:
        return len(self.products)

    def __iter__(self):
        return iter(self.products)
