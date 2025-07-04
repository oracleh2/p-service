<template>
    <div class="h-full">
        <Line
            :data="chartData"
            :options="chartOptions"
            :key="chartKey"
        />
    </div>
</template>

<script setup>
import {computed, ref, watch} from 'vue'
import {Line} from 'vue-chartjs'

const props = defineProps({
    data: {
        type: Array,
        default: () => []
    }
})

const chartKey = ref(0)

const chartData = computed(() => {
    if (!props.data || props.data.length === 0) {
        return {labels: [], datasets: []}
    }

    const labels = props.data.map(item => item.time)
    const rates = props.data.map(item => item.rate)

    return {
        labels,
        datasets: [
            {
                label: 'Success Rate',
                data: rates,
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 6
            }
        ]
    }
})

const chartOptions = computed(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            display: false
        }
    },
    scales: {
        x: {
            display: true,
            grid: {
                display: false
            }
        },
        y: {
            display: true,
            min: 0,
            max: 100,
            ticks: {
                callback: function (value) {
                    return value + '%'
                }
            }
        }
    }
}))

watch(() => props.data, () => {
    chartKey.value++
}, {deep: true})
</script>
