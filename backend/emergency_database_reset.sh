#!/bin/bash
# emergency_database_reset.sh - Экстренный сброс базы данных и Alembic

echo "🚨 Экстренный сброс базы данных и Alembic..."

# 1. Удаляем проблемную миграцию
echo "🗑️ Удаляем проблемную миграцию..."
rm -f alembic/versions/d8e644cbed4c_fix_rotation_methods.py

# 2. Проверяем, какие миграции остались
echo "📋 Оставшиеся миграции:"
ls -la alembic/versions/

# 3. Полностью очищаем базу данных
echo "🗄️ Полностью очищаем базу данных..."
psql -d mobile_proxy -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
"

# 4. Применяем исходную схему из init.sql
echo "🔧 Применяем исходную схему из init.sql..."
psql -d mobile_proxy -f init.sql

# 5. Полностью сбрасываем Alembic
echo "🔄 Полностью сбрасываем Alembic..."
psql -d mobile_proxy -c "DROP TABLE IF EXISTS alembic_version CASCADE;"

# 6. Инициализируем Alembic заново
echo "🚀 Инициализируем Alembic заново..."
alembic stamp base

# 7. Проверяем состояние
echo "🔍 Проверяем состояние..."
alembic current

# 8. Проверяем структуру таблиц
echo "📊 Проверяем структуру основных таблиц..."
psql -d mobile_proxy -c "\d+ proxy_devices"
psql -d mobile_proxy -c "\d+ rotation_config"

# 9. Проверяем ограничения на методы ротации
echo "🔒 Проверяем ограничения на методы ротации..."
psql -d mobile_proxy -c "
SELECT conname, consrc
FROM pg_constraint
WHERE conrelid = 'rotation_config'::regclass
AND contype = 'c'
AND conname LIKE '%rotation_method%';
"

echo ""
echo "✅ База данных полностью сброшена к исходному состоянию!"
echo ""
echo "📋 Текущее состояние:"
echo "- База данных: восстановлена из init.sql"
echo "- Alembic: сброшен к base"
echo "- Проблемные миграции: удалены"
echo ""
echo "💡 Теперь можете работать с базой данных как есть, или:"
echo "1. Создать новую миграцию: alembic revision --autogenerate -m 'Initial migration'"
echo "2. Применить миграцию: alembic upgrade head"
