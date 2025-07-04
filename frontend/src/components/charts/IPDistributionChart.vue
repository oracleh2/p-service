<template>
    <div class="h-full">
        <Doughnut
            :data="chartData"
            :options="chartOptions"
            :key="chartKey"
        />
    </div>
</template>

<script setup>
import {computed, ref, watch} from 'vue'
import {Doughnut} from 'vue-chartjs'
import {
    Chart as ChartJS,
    ArcElement,
    Tooltip,
    Legend
} from 'chart.js'

ChartJS.register(ArcElement, Tooltip, Legend)

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

    const labels = props.data.map(item => item.operator)
    const counts = props.data.map(item => item.count)
    const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']

    return {
        labels,
        datasets: [
            {
                data: counts,
                backgroundColor: colors.slice(0, labels.length),
                borderColor: colors.slice(0, labels.length),
                borderWidth: 2,
                hoverOffset: 4
            }
        ]
    }
})

const chartOptions = computed(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: 'bottom',
            labels: {
                padding: 20,
                usePointStyle: true
            }
        },
        tooltip: {
            callbacks: {
                label: function (context) {
                    const label = context.label || ''
                    const value = context.parsed || 0
                    const total = context.dataset.data.reduce((a, b) => a + b, 0)
                    const percentage = ((value / total) * 100).toFixed(1)
                    return `${label}: ${value} (${percentage}%)`
                }
            }
        }
    },
    cutout: '50%'
}))

watch(() => props.data, () => {
    chartKey.value++
}, {deep: true})
</script>
