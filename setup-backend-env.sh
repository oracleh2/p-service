#!/bin/bash
# setup-backend-env.sh - Настройка виртуального окружения для backend

set -e

echo "🐍 Настройка виртуального окружения для Mobile Proxy Service Backend"
echo ""

# Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Пожалуйста, запустите скрипт из корня проекта (где находится docker-compose.yml)"
    exit 1
fi

# Переходим в директорию backend
cd backend

echo "📂 Рабочая директория: $(pwd)"
echo ""

# Проверяем наличие Python
echo "🔍 Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.11+ в WSL:"
    echo "   sudo apt update"
    echo "   sudo apt install python3 python3-pip python3-venv python3-dev"
    exit 1
fi

python_version=$(python3 --version)
echo "✅ Найден: $python_version"

# Проверяем версию Python (нужен 3.11+)
python_major=$(python3 -c "import sys; print(sys.version_info.major)")
python_minor=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 11 ]); then
    echo "⚠️  Рекомендуется Python 3.11+, но будем продолжать с $python_version"
fi

# Проверяем наличие venv модуля
echo ""
echo "🔍 Проверка python3-venv..."
if ! python3 -c "import venv" 2>/dev/null; then
    echo "❌ Модуль venv не найден. Установите его:"
    echo "   sudo apt install python3-venv"
    exit 1
fi
echo "✅ Модуль venv доступен"

# Создаем виртуальное окружение
echo ""
echo "🔧 Создание виртуального окружения..."

if [ -d "venv" ]; then
    echo "⚠️  Директория venv уже существует"
    read -p "Пересоздать виртуальное окружение? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Удаление старого окружения..."
        rm -rf venv
    else
        echo "📋 Используем существующее окружение"
    fi
fi

if [ ! -d "venv" ]; then
    echo "🔨 Создание нового виртуального окружения..."
    python3 -m venv venv
    echo "✅ Виртуальное окружение создано"
fi

# Активация виртуального окружения
echo ""
echo "🔄 Активация виртуального окружения..."
source venv/bin/activate

# Проверяем активацию
if [ "$VIRTUAL_ENV" != "" ]; then
    echo "✅ Виртуальное окружение активировано: $VIRTUAL_ENV"
else
    echo "❌ Не удалось активировать виртуальное окружение"
    exit 1
fi

# Обновляем pip
echo ""
echo "⬆️  Обновление pip..."
pip install --upgrade pip
echo "✅ pip обновлен до версии: $(pip --version)"

# Устанавливаем зависимости
echo ""
echo "📦 Установка зависимостей..."

if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден в директории backend/"
    exit 1
fi

echo "📋 Устанавливаем пакеты из requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✅ Зависимости успешно установлены!"

# Проверяем установку ключевых пакетов
echo ""
echo "🔍 Проверка ключевых пакетов..."

packages_to_check=(
    "fastapi"
    "uvicorn"
    "sqlalchemy"
    "asyncpg"
    "redis"
    "pydantic"
)

for package in "${packages_to_check[@]}"; do
    if pip show "$package" &> /dev/null; then
        version=$(pip show "$package" | grep Version | cut -d' ' -f2)
        echo "  ✅ $package: $version"
    else
        echo "  ❌ $package: НЕ УСТАНОВЛЕН"
    fi
done

# Создаем скрипт активации
echo ""
echo "📝 Создание скрипта активации..."

cat > activate-env.sh << 'EOF'
#!/bin/bash
# activate-env.sh - Активация виртуального окружения для разработки

if [ -f "venv/bin/activate" ]; then
    echo "✅ Активация виртуального окружения..."
    echo "🐍 Используйте команду: source activate-env.sh"
    echo "📦 Или: source venv/bin/activate"
    echo ""
    echo "Для запуска сервера разработки:"
    echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

    # Если запущен через source, активируем
    if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
        source venv/bin/activate
        echo "✅ Окружение активировано в текущей сессии"
    fi
else
    echo "❌ Виртуальное окружение не найдено"
fi
EOF

chmod +x activate-env.sh
echo "✅ Создан скрипт activate-env.sh"

# Создаем .env файл для backend если его нет
echo ""
echo "⚙️  Проверка конфигурации..."

if [ ! -f ".env" ]; then
    echo "📝 Создание .env файла для backend..."
    cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET_KEY=dev-jwt-secret-key-change-in-production

# Proxy settings
DEFAULT_ROTATION_INTERVAL=600
MAX_DEVICES=50
MAX_REQUESTS_PER_MINUTE=100

# Development
DEBUG=true
RELOAD=true
LOG_LEVEL=DEBUG

# API settings
API_V1_STR=/api/v1
PROJECT_NAME=Mobile Proxy Service
PROJECT_VERSION=1.0.0
EOF
    echo "✅ Создан .env файл"
else
    echo "📋 .env файл уже существует"
fi

echo ""
echo "🎉 Настройка виртуального окружения завершена!"
echo ""
echo "📋 Что дальше:"
echo ""
echo "1️⃣  Убедитесь, что инфраструктурные сервисы запущены:"
echo "   cd .."
echo "   ./start-dev.sh"
echo ""
echo "2️⃣  Активируйте виртуальное окружение (в текущей сессии уже активно):"
echo "   source venv/bin/activate"
echo "   # или используйте скрипт:"
echo "   ./activate-env.sh"
echo ""
echo "3️⃣  Запустите сервер разработки:"
echo "   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "4️⃣  Проверьте работу:"
echo "   curl http://localhost:8000/health"
echo "   # или откройте http://localhost:8000/docs в браузере"
echo ""
echo "🔧 Полезные команды:"
echo "   pip list                    # Список установленных пакетов"
echo "   pip freeze > requirements.txt  # Обновить зависимости"
echo "   deactivate                 # Выйти из виртуального окружения"
echo ""
echo "📁 Текущее виртуальное окружение:"
echo "   Путь: $VIRTUAL_ENV"
echo "   Python: $(which python)"
echo "   pip: $(which pip)"
echo ""
echo "🚀 Готово к разработке!"
