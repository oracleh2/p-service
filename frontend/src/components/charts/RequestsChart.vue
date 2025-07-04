<template>
    <div class="h-80">
        <Line
            :data="chartData"
            :options="chartOptions"
            :key="chartKey"
        />
    </div>
</template>

<script setup>
import {computed, ref, watch} from 'vue'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler
} from 'chart.js'
import {Line} from 'vue-chartjs'

// Register Chart.js components
ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler
)

// Props
const props = defineProps({
    data: {
        type: Array,
        default: () => []
    }
})

// Reactive key for chart updates
const chartKey = ref(0)

// Chart data
const chartData = computed(() => {
    if (!props.data || props.data.length === 0) {
        return {
            labels: [],
            datasets: []
        }
    }

    const labels = props.data.map(item => item.time)
    const requestsData = props.data.map(item => item.requests)
    const successData = props.data.map(item => item.success)

    return {
        labels,
        datasets: [
            {
                label: 'Total Requests',
                data: requestsData,
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointBackgroundColor: 'rgb(59, 130, 246)',
                pointBorderColor: 'white',
                pointBorderWidth: 2
            },
            {
                label: 'Successful Requests',
                data: successData,
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointBackgroundColor: 'rgb(34, 197, 94)',
                pointBorderColor: 'white',
                pointBorderWidth: 2
            }
        ]
    }
})

// Chart options
const chartOptions = computed(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
        mode: 'index',
        intersect: false
    },
    plugins: {
        legend: {
            display: true,
            position: 'top',
            labels: {
                usePointStyle: true,
                pointStyle: 'circle',
                padding: 20,
                font: {
                    size: 12,
                    family: 'Inter, system-ui, sans-serif'
                }
            }
        },
        tooltip: {
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            titleColor: 'white',
            bodyColor: 'white',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            cornerRadius: 8,
            displayColors: true,
            callbacks: {
                title: function (context) {
                    return `Time: ${context[0].label}`
                },
                label: function (context) {
                    return `${context.dataset.label}: ${context.parsed.y.toLocaleString()}`
                }
            }
        }
    },
    scales: {
        x: {
            display: true,
            title: {
                display: true,
                text: 'Time (24h)',
                font: {
                    size: 12,
                    family: 'Inter, system-ui, sans-serif'
                }
            },
            grid: {
                display: true,
                color: 'rgba(0, 0, 0, 0.05)'
            },
            ticks: {
                font: {
                    size: 11,
                    family: 'Inter, system-ui, sans-serif'
                },
                maxTicksLimit: 12
            }
        },
        y: {
            display: true,
            title: {
                display: true,
                text: 'Requests',
                font: {
                    size: 12,
                    family: 'Inter, system-ui, sans-serif'
                }
            },
            grid: {
                display: true,
                color: 'rgba(0, 0, 0, 0.05)'
            },
            ticks: {
                font: {
                    size: 11,
                    family: 'Inter, system-ui, sans-serif'
                },
                callback: function (value) {
                    if (value >= 1000) {
                        return (value / 1000).toFixed(1) + 'K'
                    }
                    return value
                }
            },
            beginAtZero: true
        }
    },
    elements: {
        line: {
            borderWidth: 2
        },
        point: {
            hoverBorderWidth: 3
        }
    }
}))

// Watch for data changes and update chart
watch(
    () => props.data,
    () => {
        chartKey.value++
    },
    {deep: true}
)
</script>
