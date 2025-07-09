#!/bin/bash

# Скрипт мониторинга внешнего IP с автоматической сменой
# Проверяет IP каждую минуту в течение 3 часов

INTERFACE="enx0c5b8f279a64"
DURATION=10800  # 3 часа в секундах
CHECK_INTERVAL=60  # 1 минута

# Переменные для статистики
declare -a IP_CHANGES
declare -a CHANGE_TIMES
CURRENT_IP=""
PREVIOUS_IP=""
START_TIME=$(date +%s)
LAST_CHECK_TIME=$START_TIME
CHECKS_COUNT=0
CHANGES_COUNT=0
STOPPED_BY_USER=false

# Файл для сохранения результатов
RESULT_FILE="ip_monitoring_$(date +%Y%m%d_%H%M%S).log"

# Функция получения внешнего IP
get_external_ip() {
    local ip=$(curl --interface "$INTERFACE" -s --connect-timeout 10 --max-time 15 2ip.ru 2>/dev/null)
    # Очищаем от лишних символов и оставляем только IP
    echo "$ip" | grep -oE '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$' | head -1
}

# Функция обработки сигнала прерывания
handle_interrupt() {
    echo ""
    echo "⚠️ Получен сигнал прерывания. Останавливаю проверки..."
    STOPPED_BY_USER=true

    # Предлагаем возобновить
    echo ""
    read -p "Хотите возобновить проверки? (y/n): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔄 Возобновляю проверки..."
        STOPPED_BY_USER=false
        return 0
    else
        echo "🛑 Завершаю мониторинг..."
        return 1
    fi
}

# Функция записи статистики в файл
write_statistics() {
    local end_time=$(date +%s)
    local total_duration=$((end_time - START_TIME))
    local hours=$((total_duration / 3600))
    local minutes=$(((total_duration % 3600) / 60))
    local seconds=$((total_duration % 60))

    echo "📊 IP MONITORING STATISTICS" > "$RESULT_FILE"
    echo "===========================" >> "$RESULT_FILE"
    echo "" >> "$RESULT_FILE"
    echo "📅 Период мониторинга:" >> "$RESULT_FILE"
    echo "  Начало: $(date -d "@$START_TIME" "+%Y-%m-%d %H:%M:%S")" >> "$RESULT_FILE"
    echo "  Конец:  $(date -d "@$end_time" "+%Y-%m-%d %H:%M:%S")" >> "$RESULT_FILE"
    echo "  Продолжительность: ${hours}ч ${minutes}м ${seconds}с" >> "$RESULT_FILE"
    echo "" >> "$RESULT_FILE"

    echo "📈 Общая статистика:" >> "$RESULT_FILE"
    echo "  Всего проверок: $CHECKS_COUNT" >> "$RESULT_FILE"
    echo "  Обнаружено смен IP: $CHANGES_COUNT" >> "$RESULT_FILE"

    if [ $CHANGES_COUNT -gt 0 ]; then
        echo "  Частота смен: $(echo "scale=2; $CHANGES_COUNT * 3600 / $total_duration" | bc -l) смен/час" >> "$RESULT_FILE"
    else
        echo "  Частота смен: 0 смен/час" >> "$RESULT_FILE"
    fi

    echo "" >> "$RESULT_FILE"

    # Статистика интервалов между сменами
    if [ $CHANGES_COUNT -gt 1 ]; then
        echo "⏱️ Интервалы между сменами IP:" >> "$RESULT_FILE"
        local total_interval=0
        local min_interval=999999
        local max_interval=0

        for ((i=1; i<$CHANGES_COUNT; i++)); do
            local interval=$((CHANGE_TIMES[i] - CHANGE_TIMES[i-1]))
            local interval_min=$((interval / 60))
            local interval_sec=$((interval % 60))

            echo "  Смена $i: ${interval_min}м ${interval_sec}с" >> "$RESULT_FILE"

            total_interval=$((total_interval + interval))
            if [ $interval -lt $min_interval ]; then
                min_interval=$interval
            fi
            if [ $interval -gt $max_interval ]; then
                max_interval=$interval
            fi
        done

        local avg_interval=$((total_interval / (CHANGES_COUNT - 1)))
        local avg_min=$((avg_interval / 60))
        local avg_sec=$((avg_interval % 60))
        local min_min=$((min_interval / 60))
        local min_sec=$((min_interval % 60))
        local max_min=$((max_interval / 60))
        local max_sec=$((max_interval % 60))

        echo "" >> "$RESULT_FILE"
        echo "📊 Статистика интервалов:" >> "$RESULT_FILE"
        echo "  Среднее время между сменами: ${avg_min}м ${avg_sec}с" >> "$RESULT_FILE"
        echo "  Минимальный интервал: ${min_min}м ${min_sec}с" >> "$RESULT_FILE"
        echo "  Максимальный интервал: ${max_min}м ${max_sec}с" >> "$RESULT_FILE"
    fi

    echo "" >> "$RESULT_FILE"
    echo "🔄 Детальная история смен IP:" >> "$RESULT_FILE"

    if [ $CHANGES_COUNT -gt 0 ]; then
        for ((i=0; i<$CHANGES_COUNT; i++)); do
            local change_time=$(date -d "@${CHANGE_TIMES[i]}" "+%Y-%m-%d %H:%M:%S")
            echo "  $((i+1)). $change_time - ${IP_CHANGES[i]}" >> "$RESULT_FILE"
        done
    else
        echo "  Смен IP не обнаружено" >> "$RESULT_FILE"
    fi

    echo "" >> "$RESULT_FILE"
    echo "ℹ️ Дополнительная информация:" >> "$RESULT_FILE"
    echo "  Интерфейс: $INTERFACE" >> "$RESULT_FILE"
    echo "  Интервал проверок: ${CHECK_INTERVAL}с" >> "$RESULT_FILE"
    echo "  Сервис проверки: 2ip.ru" >> "$RESULT_FILE"

    if [ "$STOPPED_BY_USER" = true ]; then
        echo "  Остановлено: пользователем" >> "$RESULT_FILE"
    else
        echo "  Остановлено: по таймауту" >> "$RESULT_FILE"
    fi
}

# Функция основного цикла мониторинга
main_monitoring_loop() {
    while true; do
        local current_time=$(date +%s)

        # Проверка на превышение времени
        if [ $((current_time - START_TIME)) -ge $DURATION ]; then
            echo ""
            echo "⏰ Достигнуто максимальное время мониторинга (3 часа)"
            break
        fi

        # Получаем текущий IP
        CURRENT_IP=$(get_external_ip)
        CHECKS_COUNT=$((CHECKS_COUNT + 1))

        # Проверяем на изменение IP
        if [ -n "$CURRENT_IP" ] && [ "$CURRENT_IP" != "$PREVIOUS_IP" ] && [ -n "$PREVIOUS_IP" ]; then
            CHANGES_COUNT=$((CHANGES_COUNT + 1))
            IP_CHANGES+=("$PREVIOUS_IP → $CURRENT_IP")
            CHANGE_TIMES+=($current_time)

            echo "🔄 Смена IP: $PREVIOUS_IP → $CURRENT_IP ($(date "+%H:%M:%S"))"
        fi

        # Обновляем предыдущий IP
        if [ -n "$CURRENT_IP" ]; then
            PREVIOUS_IP="$CURRENT_IP"
        fi

        # Настройка перехвата сигнала прерывания
        trap 'handle_interrupt || break' INT

        # Ожидание до следующей проверки
        sleep $CHECK_INTERVAL
    done
}

# Основная функция
main() {
    echo "🚀 Запуск мониторинга внешнего IP"
    echo "================================="
    echo "Интерфейс: $INTERFACE"
    echo "Интервал проверок: $CHECK_INTERVAL секунд"
    echo "Максимальное время: 3 часа"
    echo "Файл результатов: $RESULT_FILE"
    echo ""
    echo "💡 Для остановки нажмите Ctrl+C"
    echo ""

    # Получаем начальный IP
    echo "🔍 Получение начального IP..."
    CURRENT_IP=$(get_external_ip)

    if [ -z "$CURRENT_IP" ]; then
        echo "❌ Не удалось получить внешний IP. Проверьте подключение."
        exit 1
    fi

    echo "📋 Начальный IP: $CURRENT_IP"
    PREVIOUS_IP="$CURRENT_IP"

    echo ""
    echo "🔄 Начинаю мониторинг..."
    echo "========================"

    # Запуск основного цикла
    main_monitoring_loop

    echo ""
    echo "📊 Формирую статистику..."

    # Записываем статистику в файл
    write_statistics

    echo ""
    echo "✅ Мониторинг завершен!"
    echo "📄 Статистика сохранена в файл: $RESULT_FILE"
    echo ""

    # Показываем краткую сводку
    echo "📈 Краткая сводка:"
    echo "  Проверок выполнено: $CHECKS_COUNT"
    echo "  Смен IP обнаружено: $CHANGES_COUNT"

    if [ $CHANGES_COUNT -gt 0 ]; then
        local total_duration=$(($(date +%s) - START_TIME))
        local frequency=$(echo "scale=2; $CHANGES_COUNT * 3600 / $total_duration" | bc -l)
        echo "  Частота смен: $frequency смен/час"

        if [ $CHANGES_COUNT -gt 1 ]; then
            local total_interval=0
            for ((i=1; i<$CHANGES_COUNT; i++)); do
                total_interval=$((total_interval + CHANGE_TIMES[i] - CHANGE_TIMES[i-1]))
            done
            local avg_interval=$((total_interval / (CHANGES_COUNT - 1)))
            local avg_min=$((avg_interval / 60))
            local avg_sec=$((avg_interval % 60))
            echo "  Среднее время между сменами: ${avg_min}м ${avg_sec}с"
        fi
    else
        echo "  Смены IP не обнаружены"
    fi
}

# Проверка зависимостей
if ! command -v curl >/dev/null 2>&1; then
    echo "❌ curl не установлен. Установите: sudo apt install curl"
    exit 1
fi

if ! command -v bc >/dev/null 2>&1; then
    echo "❌ bc не установлен. Установите: sudo apt install bc"
    exit 1
fi

# Запуск основной функции
main "$@"
