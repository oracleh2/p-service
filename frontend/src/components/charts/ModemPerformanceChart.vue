<template>
    <div class="h-full">
        <Bar
            :data="chartData"
            :options="chartOptions"
            :key="chartKey"
        />
    </div>
</template>

<script setup>
import {computed, ref, watch} from 'vue'
import {Bar} from 'vue-chartjs'
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    Title,
    Tooltip,
    Legend
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

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

    const labels = props.data.map(item => item.name)
    const requests = props.data.map(item => item.requests)
    const successRates = props.data.map(item => item.successRate)

    return {
        labels,
        datasets: [
            {
                label: 'Requests',
                data: requests,
                backgroundColor: 'rgba(59, 130, 246, 0.8)',
                borderColor: 'rgb(59, 130, 246)',
                borderWidth: 1,
                yAxisID: 'y'
            },
            {
                label: 'Success Rate (%)',
                data: successRates,
                backgroundColor: 'rgba(34, 197, 94, 0.8)',
                borderColor: 'rgb(34, 197, 94)',
                borderWidth: 1,
                yAxisID: 'y1'
            }
        ]
    }
})

const chartOptions = computed(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: 'top'
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
            type: 'linear',
            display: true,
            position: 'left',
            title: {
                display: true,
                text: 'Requests'
            }
        },
        y1: {
            type: 'linear',
            display: true,
            position: 'right',
            title: {
                display: true,
                text: 'Success Rate (%)'
            },
            grid: {
                drawOnChartArea: false
            },
            min: 0,
            max: 100
        }
    }
}))

watch(() => props.data, () => {
    chartKey.value++
}, {deep: true})
</script>
