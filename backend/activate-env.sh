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
