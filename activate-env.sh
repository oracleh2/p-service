#!/bin/bash
# activate-env.sh - Активация виртуального окружения для разработки

if [ -f "backend/venv/bin/activate" ]; then
    echo "✅ Активация виртуального окружения..."
    echo "🐍 Используйте команду: source activate-env.sh"
    echo "📦 Или: source backend/venv/bin/activate"
    echo ""
    echo "Для запуска сервера разработки:"
    echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

    # Если запущен через source, активируем
    if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
        source backend/venv/bin/activate
        echo "✅ Окружение активировано в текущей сессии"
    fi
else
    echo "❌ Виртуальное окружение не найдено"
fi
