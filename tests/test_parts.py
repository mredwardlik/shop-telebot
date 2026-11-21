"""Settings, views, catalog and the entry point."""

import pytest
from conftest import TOKEN

from shop_telebot import __main__ as entry
from shop_telebot.catalog import Catalog
from shop_telebot.settings import ConfigError, load_settings
from shop_telebot.views import Views


def write_config(path, text):
    path.write_text(text, encoding='utf-8')
    return path


def test_settings(tmp_path):
    config = write_config(tmp_path / 'config.env', f'TOKEN={TOKEN}\nADMINS=1, 2,3\nBUY_BUTTON=Взять\n')
    settings = load_settings(config, environ={})
    assert settings.token == TOKEN
    assert settings.admins == {1, 2, 3}
    assert settings.views_dir == tmp_path / 'views'
    assert settings.products_dir == tmp_path / 'views' / 'products'
    assert settings.buy_button == 'Взять'
    assert settings.ordered_button == '✅ Заявка отправлена'


def test_environment_overrides_file(tmp_path):
    config = write_config(tmp_path / 'config.env', 'TOKEN=\nADMINS=1\n')
    settings = load_settings(config, environ={'TOKEN': TOKEN, 'ADMINS': '5'})
    assert settings.token == TOKEN and settings.admins == {5}


def test_only_environment(tmp_path):
    settings = load_settings(tmp_path / 'config.env', environ={'TOKEN': TOKEN})
    assert settings.admins == frozenset()


def test_missing_config(tmp_path):
    with pytest.raises(ConfigError, match='config.example.env'):
        load_settings(tmp_path / 'config.env', environ={})


def test_example_config_needs_a_token():
    from conftest import ROOT
    with pytest.raises(ConfigError, match='BotFather'):
        load_settings(ROOT / 'config.example.env', environ={})


@pytest.mark.parametrize('admins', ['abc', '12,x'])
def test_wrong_admins(tmp_path, admins):
    config = write_config(tmp_path / 'config.env', f'TOKEN={TOKEN}\nADMINS={admins}\n')
    with pytest.raises(ConfigError, match='userinfobot'):
        load_settings(config, environ={})


def test_views_fallbacks(tmp_path, caplog):
    views = Views(tmp_path)
    assert 'Каталог' in views.render('menu')
    assert 'not found' in caplog.text
    assert set(views.missing()) == {'start', 'start_admin', 'menu', 'sent', 'sent_admin',
                                    'no_product', 'no_command'}


def test_view_with_wrong_placeholder(tmp_path, caplog):
    (tmp_path / 'start.html').write_text('Hi {user.first_name} {oops}', encoding='utf-8')
    assert Views(tmp_path).render('start', user={'first_name': 'A'}) == 'Hi {user.first_name} {oops}'
    assert 'wrong placeholder' in caplog.text


def test_view_of_the_first_version(tmp_path):
    (tmp_path / 'sent_admin.html').write_text(
        '<a href="tg://user?id={call.from_user.id}">{call.from_user.full_name}</a> '
        'хочет купить {product.current}.', encoding='utf-8')
    call = {'from_user': type('User', (), {'id': 7, 'full_name': 'Bob'})()}
    text = Views(tmp_path).render('sent_admin', call=call, product={'current': 'Брюки'})
    assert text == '<a href="tg://user?id=7">Bob</a> хочет купить Брюки.'


def test_catalog(tmp_path):
    (tmp_path / '2 Брюки.html').write_text('b', encoding='utf-8')
    (tmp_path / '1 Рубашки.html').write_text('r', encoding='utf-8')
    (tmp_path / '1 Рубашки.webp').write_bytes(b'img')
    (tmp_path / 'notes.txt').write_text('ignored')
    catalog = Catalog(tmp_path)
    assert catalog.names == ['Рубашки', 'Брюки']
    assert catalog.get('РУБАШКИ').image == tmp_path / '1 Рубашки.webp'
    assert catalog.get('Брюки').image is None
    assert catalog.by_id(catalog.get('Брюки').id).description == 'b'
    assert catalog.get('Шапки') is None


def test_catalog_skips_duplicates(tmp_path, caplog):
    (tmp_path / '1 Брюки.html').write_text('first', encoding='utf-8')
    (tmp_path / '2 брюки.html').write_text('second', encoding='utf-8')
    catalog = Catalog(tmp_path)
    assert len(catalog) == 1 and catalog.get('Брюки').description == 'first'
    assert 'twice' in caplog.text


def test_check_command(tmp_path, monkeypatch, capsys):
    from conftest import ROOT
    import shutil
    shutil.copytree(ROOT / 'views', tmp_path / 'views')
    write_config(tmp_path / 'config.env', f'TOKEN={TOKEN}\nADMINS=1\n')
    monkeypatch.delenv('TOKEN', raising=False)
    assert entry.main(['--config', str(tmp_path / 'config.env'), '--check']) == 0
    out = capsys.readouterr().out
    assert 'Products (2): Брюки, Рубашки' in out and 'OK' in out

    (tmp_path / 'views' / 'menu.html').unlink()
    assert entry.main(['--config', str(tmp_path / 'config.env'), '--check']) == 1


def test_bad_config_exit_code(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv('TOKEN', raising=False)
    assert entry.main(['--config', str(tmp_path / 'config.env')]) == 2
    assert 'config.example.env' in caplog.text


def test_wrong_token(tmp_path, monkeypatch, telegram, caplog):
    monkeypatch.delenv('TOKEN', raising=False)
    write_config(tmp_path / 'config.env', f'TOKEN={TOKEN}\n')
    telegram.errors[('getMe', None)] = (401, 'Unauthorized')
    assert entry.main(['--config', str(tmp_path / 'config.env')]) == 2
    assert "doesn't accept the token" in caplog.text
