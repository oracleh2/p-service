<!-- frontend/src/views/DeviceDebugView.vue -->
<template>
  <div class="device-debug-view">
    <DeviceDebug />
  </div>
</template>

<script>
import DeviceDebug from '../components/DeviceDebug.vue'

export default {
  name: 'DeviceDebugView',
  components: {
    DeviceDebug
  },
  meta: {
    title: 'Отладка устройств',
    requiresAuth: true,
    requiresAdmin: true
  }
}
</script>

<style scoped>
.device-debug-view {
  min-height: 100vh;
}
</style>
