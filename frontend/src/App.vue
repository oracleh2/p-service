<template>
    <div id="app" class="min-h-screen bg-gray-50">
        <!-- Loading overlay -->
        <div v-if="isInitializing" class="fixed inset-0 bg-white flex-center z-50">
            <div class="text-center">
                <div class="loading-spinner w-8 h-8 mx-auto mb-4"></div>
                <p class="text-gray-600">Initializing...</p>
            </div>
        </div>

        <!-- Main app content -->
        <div v-else>
            <!-- Authenticated layout -->
            <div v-if="isAuthenticated" class="flex h-screen bg-gray-50">
                <!-- Sidebar -->
                <AppSidebar/>

                <!-- Main content -->
                <div class="flex-1 flex flex-col overflow-hidden">
                    <!-- Header -->
                    <AppHeader/>

                    <!-- Page content -->
                    <main class="flex-1 overflow-x-hidden overflow-y-auto bg-gray-50">
                        <div class="container-wide py-6">
                            <router-view/>
                        </div>
                    </main>
                </div>
            </div>

            <!-- Unauthenticated layout -->
            <div v-else class="min-h-screen">
                <router-view/>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, onMounted, computed} from 'vue'
import {useAuthStore} from '@/stores/auth'
import AppSidebar from '@/components/AppSidebar.vue'
import AppHeader from '@/components/AppHeader.vue'

const authStore = useAuthStore()
const isInitializing = ref(true)

const isAuthenticated = computed(() => authStore.isAuthenticated)

onMounted(async () => {
    try {
        // Try to restore authentication
        await authStore.restoreAuth()
    } catch (error) {
        console.error('Failed to restore auth:', error)
    } finally {
        isInitializing.value = false
    }
})
</script>

<style scoped>
/* Component-specific styles */
</style>
