#!/bin/bash

# Скрипт для автоматического подбора оптимальных таймаутов ротации
# Проводит серию тестов с разными таймаутами и находит оптимальные значения

ROTATION_SCRIPT="./improved_storage_mode_rotation.sh"
RESULTS_FILE="timeout_optimization_results.txt"

# Проверяем наличие основного скрипта
if [ ! -f "$ROTATION_SCRIPT" ]; then
    echo "❌ Не найден скрипт ротации: $ROTATION_SCRIPT"
    echo "Сохраните предыдущий скрипт как improved_storage_mode_rotation.sh"
    exit 1
fi

chmod +x "$ROTATION_SCRIPT"

echo "🧪 Автоматическая оптимизация таймаутов ротации"
echo "=============================================="
echo "📋 Результаты будут сохранены в: $RESULTS_FILE"
echo ""

# Очищаем файл результатов
cat > "$RESULTS_FILE" << EOF
# Результаты оптимизации таймаутов ротации
# Дата: $(date)
# Формат: storage_timeout,restore_timeout,interface_timeout,dhcp_timeout,success,initial_ip,new_ip,total_time

EOF

# Наборы таймаутов для тестирования
declare -a TEST_CONFIGS=(
    # Быстрые настройки
    "5,10,30,15"
    "5,15,30,15"
    "10,15,30,15"
    "10,20,30,15"

    # Стандартные настройки
    "15,20,60,20"
    "15,25,60,20"
    "20,25,60,20"
    "20,30,60,20"

    # Медленные но надежные
    "25,35,90,25"
    "30,40,90,25"
    "30,45,120,30"
    "35,50,120,30"
)

TOTAL_TESTS=${#TEST_CONFIGS[@]}
CURRENT_TEST=0
SUCCESSFUL_TESTS=0

echo "📊 Запланировано тестов: $TOTAL_TESTS"
echo "⏱️  Ориентировочное время: $((TOTAL_TESTS * 3)) минут"
echo ""

# Функция проведения теста
run_test() {
    local config="$1"
    local test_num="$2"

    IFS=',' read -r storage_timeout restore_timeout interface_timeout dhcp_timeout <<< "$config"

    echo "🔬 Тест $test_num/$TOTAL_TESTS"
    echo "📋 Таймауты: Storage=${storage_timeout}s, Restore=${restore_timeout}s, Interface=${interface_timeout}s, DHCP=${dhcp_timeout}s"

    # Записываем начало теста
    echo "# Тест $test_num: $config" >> "$RESULTS_FILE"

    # Запускаем тест
    local start_time=$(date +%s)

    # Захватываем вывод скрипта
    local test_output
    test_output=$($ROTATION_SCRIPT -s "$storage_timeout" -r "$restore_timeout" -i "$interface_timeout" -d "$dhcp_timeout" 2>&1)
    local exit_code=$?

    local end_time=$(date +%s)
    local total_time=$((end_time - start_time))

    # Извлекаем IP адреса из вывода
    local initial_ip=$(echo "$test_output" | grep "Начальный внешний IP:" | grep -o '[0-9.]*' | tail -1)
    local new_ip=$(echo "$test_output" | grep "Новый IP:" | grep -o '[0-9.]*' | tail -1)

    # Проверяем успешность
    local success="false"
    if [ $exit_code -eq 0 ]; then
        success="true"
        SUCCESSFUL_TESTS=$((SUCCESSFUL_TESTS + 1))
        echo "  ✅ Успешно! IP: $initial_ip → $new_ip (${total_time}s)"
    else
        echo "  ❌ Неудачно (${total_time}s)"
    fi

    # Сохраняем результат
    echo "$storage_timeout,$restore_timeout,$interface_timeout,$dhcp_timeout,$success,$initial_ip,$new_ip,$total_time" >> "$RESULTS_FILE"

    # Пауза между тестами
    echo "⏳ Пауза между тестами (30s)..."
    sleep 30

    echo ""
}

# Проводим все тесты
echo "🚀 Начинаем тестирование..."
echo ""

for config in "${TEST_CONFIGS[@]}"; do
    CURRENT_TEST=$((CURRENT_TEST + 1))
    run_test "$config" "$CURRENT_TEST"
done

echo ""
echo "📊 Анализ результатов"
echo "==================="

# Анализируем результаты
echo "📋 Общая статистика:"
echo "  Всего тестов: $TOTAL_TESTS"
echo "  Успешных: $SUCCESSFUL_TESTS"
echo "  Неудачных: $((TOTAL_TESTS - SUCCESSFUL_TESTS))"
echo "  Процент успеха: $(( (SUCCESSFUL_TESTS * 100) / TOTAL_TESTS ))%"
echo ""

if [ $SUCCESSFUL_TESTS -gt 0 ]; then
    echo "✅ Успешные конфигурации:"
    echo "========================="

    # Анализируем успешные тесты
    while IFS=',' read -r storage restore interface dhcp success initial_ip new_ip total_time; do
        # Пропускаем комментарии
        if [[ "$storage" == \#* ]]; then
            continue
        fi

        if [ "$success" = "true" ]; then
            echo "  📋 $storage/$restore/$interface/${dhcp}s → IP: $initial_ip → $new_ip (${total_time}s)"
        fi
    done < "$RESULTS_FILE"

    echo ""
    echo "🏆 Рекомендации:"
    echo "==============="

    # Находим самую быструю успешную конфигурацию
    fastest_config=$(grep ",true," "$RESULTS_FILE" | sort -t',' -k8 -n | head -1)
    if [ -n "$fastest_config" ]; then
        IFS=',' read -r storage restore interface dhcp success initial_ip new_ip total_time <<< "$fastest_config"
        echo "🚀 Самая быстрая конфигурация (${total_time}s):"
        echo "    $0 -s $storage -r $restore -i $interface -d $dhcp"
    fi

    # Находим самую надежную конфигурацию (среди часто успешных)
    reliable_config=$(grep ",true," "$RESULTS_FILE" | sort -t',' -k1,4 -n | head -1)
    if [ -n "$reliable_config" ]; then
        IFS=',' read -r storage restore interface dhcp success initial_ip new_ip total_time <<< "$reliable_config"
        echo "🛡️  Надежная конфигурация (${total_time}s):"
        echo "    $0 -s $storage -r $restore -i $interface -d $dhcp"
    fi

    # Анализируем оптимальные диапазоны
    echo ""
    echo "📈 Оптимальные диапазоны:"

    # Извлекаем успешные значения
    successful_storage=$(grep ",true," "$RESULTS_FILE" | cut -d',' -f1 | sort -n)
    successful_restore=$(grep ",true," "$RESULTS_FILE" | cut -d',' -f2 | sort -n)
    successful_interface=$(grep ",true," "$RESULTS_FILE" | cut -d',' -f3 | sort -n)
    successful_dhcp=$(grep ",true," "$RESULTS_FILE" | cut -d',' -f4 | sort -n)

    if [ -n "$successful_storage" ]; then
        min_storage=$(echo "$successful_storage" | head -1)
        max_storage=$(echo "$successful_storage" | tail -1)
        echo "  Storage timeout: ${min_storage}-${max_storage}s"
    fi

    if [ -n "$successful_restore" ]; then
        min_restore=$(echo "$successful_restore" | head -1)
        max_restore=$(echo "$successful_restore" | tail -1)
        echo "  Restore timeout: ${min_restore}-${max_restore}s"
    fi

    if [ -n "$successful_interface" ]; then
        min_interface=$(echo "$successful_interface" | head -1)
        max_interface=$(echo "$successful_interface" | tail -1)
        echo "  Interface timeout: ${min_interface}-${max_interface}s"
    fi

    if [ -n "$successful_dhcp" ]; then
        min_dhcp=$(echo "$successful_dhcp" | head -1)
        max_dhcp=$(echo "$successful_dhcp" | tail -1)
        echo "  DHCP timeout: ${min_dhcp}-${max_dhcp}s"
    fi

else
    echo "❌ Успешных конфигураций не найдено"
    echo ""
    echo "🔧 Рекомендации для исправления:"
    echo "1. Проверьте подключение модема"
    echo "2. Убедитесь что модем в HiLink режиме"
    echo "3. Попробуйте увеличить таймауты"
    echo "4. Проверьте права на выполнение usb_modeswitch"
fi

echo ""
echo "💾 Детальные результаты сохранены в: $RESULTS_FILE"
echo ""
echo "🔬 Для повторного анализа используйте:"
echo "  cat $RESULTS_FILE"
echo ""
echo "📊 Для визуализации результатов:"
echo "  grep ',true,' $RESULTS_FILE | cut -d',' -f1-4,8 | sort -t',' -k5 -n"

# Создаем краткий отчет
SUMMARY_FILE="timeout_optimization_summary.txt"
cat > "$SUMMARY_FILE" << EOF
# Краткий отчет оптимизации таймаутов
# Дата: $(date)

Статистика:
- Всего тестов: $TOTAL_TESTS
- Успешных: $SUCCESSFUL_TESTS
- Процент успеха: $(( (SUCCESSFUL_TESTS * 100) / TOTAL_TESTS ))%

EOF

if [ $SUCCESSFUL_TESTS -gt 0 ]; then
    echo "Лучшие конфигурации:" >> "$SUMMARY_FILE"
    grep ",true," "$RESULTS_FILE" | sort -t',' -k8 -n | head -3 | while IFS=',' read -r storage restore interface dhcp success initial_ip new_ip total_time; do
        echo "- Storage:${storage}s Restore:${restore}s Interface:${interface}s DHCP:${dhcp}s (${total_time}s)" >> "$SUMMARY_FILE"
    done
fi

echo "📋 Краткий отчет сохранен в: $SUMMARY_FILE"
echo ""
echo "🎉 Оптимизация завершена!"
