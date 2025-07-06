#!/bin/bash
# setup-alembic.sh - Настройка Alembic (создание alembic.ini)

set -e

echo "🗃️  Настройка Alembic для миграций базы данных"
echo ""

# Проверка, что мы в директории backend
if [ ! -f "requirements.txt" ]; then
    echo "❌ Пожалуйста, запустите скрипт из директории backend/"
    echo "   cd backend && ./setup-alembic.sh"
    exit 1
fi

# Проверка наличия .env файла
if [ ! -f "../.env" ]; then
    echo "❌ Файл .env не найден в корне проекта"
    echo "   Создайте файл .env из .env.example"
    exit 1
fi

# Чтение DATABASE_URL из .env файла
echo "📋 Чтение настроек из .env файла..."
DATABASE_URL=$(grep "^DATABASE_URL=" ../.env | cut -d '=' -f2- | sed 's/^"//' | sed 's/"$//')

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL не найден в .env файле"
    echo "   Убедитесь, что в .env есть строка: DATABASE_URL=postgresql://..."
    exit 1
fi

echo "✅ DATABASE_URL найден: ${DATABASE_URL:0:30}..."

# Проверка активации виртуального окружения
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Виртуальное окружение не активировано"
    echo "   Активируйте его: source venv/bin/activate"
    echo ""
    echo "🔄 Попытка активации..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        echo "✅ Виртуальное окружение активировано"
    else
        echo "❌ Виртуальное окружение не найдено"
        echo "   Создайте его: python -m venv venv && source venv/bin/activate"
        exit 1
    fi
fi

# Проверка установки alembic
if ! pip show alembic > /dev/null 2>&1; then
    echo "📦 Установка Alembic..."
    pip install alembic
    echo "✅ Alembic установлен"
fi

# Создание alembic.ini с DATABASE_URL из .env
echo "📝 Создание alembic.ini..."
cat > alembic.ini << EOF
# A generic, single database configuration.

[alembic]
# path to migration scripts
script_location = alembic

# template used to generate migration file names; The default value is %%(rev)s_%%(slug)s
# Uncomment the line below if you want the files to be prepended with date and time
# file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s

# sys.path path, will be prepended to sys.path if present.
# defaults to the current working directory.
prepend_sys_path = .

# timezone to use when rendering the date within the migration file
# as well as the filename.
# If specified, requires the python-dateutil library that can be
# installed by adding \`alembic[tz]\` to the pip requirements
# string value is passed to dateutil.tz.gettz()
# leave blank for localtime
# timezone =

# max length of characters to apply to the
# "slug" field
# truncate_slug_length = 40

# set to 'true' to run the environment during
# the 'revision' command, regardless of autogenerate
# revision_environment = false

# set to 'true' to allow .pyc and .pyo files without
# a source .py file to be detected as revisions in the
# versions/ directory
# sourceless = false

# version path separator; As mentioned above, this is the character used to split
# version_locations. The default within new alembic.ini files is "os", which uses
# os.pathsep. If this key is omitted entirely, it falls back to the legacy
# behavior of splitting on spaces and/or commas.
# Valid values for version_path_separator are:
#
# version_path_separator = :
# version_path_separator = ;
# version_path_separator = space
version_path_separator = os

# set to 'true' to search source files recursively
# in each "version_locations" directory
# new in Alembic version 1.10
# recursive_version_locations = false

# the output encoding used when revision files
# are written from script.py.mako
# output_encoding = utf-8

sqlalchemy.url = $DATABASE_URL

[post_write_hooks]
# post_write_hooks defines scripts or Python functions that are run
# on newly generated revision scripts.  See the documentation for further
# detail and examples

# format using "black" - use the console_scripts runner, against the "black" entrypoint
# hooks = black
# black.type = console_scripts
# black.entrypoint = black
# black.options = -l 79 REVISION_SCRIPT_FILENAME

# lint with attempts to fix using "ruff" - use the exec runner, execute a binary
# hooks = ruff
# ruff.type = exec
# ruff.executable = %(here)s/.venv/bin/ruff
# ruff.options = --fix REVISION_SCRIPT_FILENAME

# Logging configuration
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
EOF

echo "✅ alembic.ini создан с DATABASE_URL из .env"

# Инициализация Alembic (создание директории migrations) только если её нет
if [ ! -d "alembic" ]; then
    echo "🚀 Инициализация Alembic..."
    alembic init alembic
    echo "✅ Alembic инициализирован"

    # Обновление env.py для работы с существующими моделями проекта
    echo "📝 Обновление alembic/env.py для работы с моделями проекта..."
    cat > alembic/env.py << 'EOF'
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Добавляем путь к приложению
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модели из существующего проекта
try:
    from app.models.base import Base
    target_metadata = Base.metadata
except ImportError:
    # Если модели не найдены, используем None
    target_metadata = None
    print("Warning: Could not import models. Make sure app.models.base exists.")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
EOF
    echo "✅ alembic/env.py обновлен для работы с существующими моделями"
else
    echo "📁 Директория alembic уже существует"
fi

echo ""
echo "✅ Alembic настроен успешно!"
echo ""
echo "📋 Следующие шаги:"
echo ""
echo "1. Создайте первую миграцию (если нужно):"
echo "   alembic revision --autogenerate -m \"Initial migration\""
echo ""
echo "2. Примените миграции:"
echo "   alembic upgrade head"
echo ""
echo "3. Для создания новых миграций в будущем:"
echo "   alembic revision --autogenerate -m \"Description of changes\""
echo ""
echo "4. Для отката миграций:"
echo "   alembic downgrade -1"
echo ""
echo "💡 DATABASE_URL автоматически взят из .env файла"
echo "💡 При изменении .env файла alembic.ini обновится автоматически"
