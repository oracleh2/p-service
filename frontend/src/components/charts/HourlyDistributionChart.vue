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

    const labels = props.data.map(item => `${item.hour}:00`)
    const requests = props.data.map(item => item.requests)

    return {
        labels,
        datasets: [
            {
                label: 'Requests',
                data: requests,
                backgroundColor: 'rgba(59, 130, 246, 0.8)',
                borderColor: 'rgb(59, 130, 246)',
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
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
            title: {
                display: true,
                text: 'Hour of Day'
            },
            grid: {
                display: false
            }
        },
        y: {
            display: true,
            title: {
                display: true,
                text: 'Requests'
            },
            beginAtZero: true
        }
    }
}))

watch(() => props.data, () => {
    chartKey.value++
}, {deep: true})
</script>
