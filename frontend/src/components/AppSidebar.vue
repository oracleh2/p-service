<template>
    <div class="hidden lg:flex lg:flex-shrink-0">
        <div class="flex flex-col w-80 xl:w-88 2xl:w-96">
            <!-- Sidebar component -->
            <div class="flex flex-col flex-grow bg-white border-r border-gray-200 pt-5 pb-4 overflow-y-auto">
                <!-- Logo -->
                <div class="flex items-center flex-shrink-0 px-6">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <div class="w-10 h-10 bg-primary-600 rounded-lg flex-center">
                                <WifiIcon class="w-6 h-6 text-white"/>
                            </div>
                        </div>
                        <div class="ml-3">
                            <h1 class="text-lg font-semibold text-gray-900">
                                Mobile Proxy
                            </h1>
                            <p class="text-sm text-gray-500">Admin Panel</p>
                        </div>
                    </div>
                </div>

                <!-- Navigation -->
                <nav class="mt-8 flex-1 px-3 space-y-1">
                    <!-- Main navigation -->
                    <div class="space-y-1">
                        <router-link
                            v-for="item in navigation"
                            :key="item.name"
                            :to="item.href"
                            :class="[
                isActiveRoute(item.href)
                  ? 'bg-primary-50 border-primary-500 text-primary-700'
                  : 'border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                'group flex items-center px-3 py-2 text-sm font-medium border-l-4 transition-colors'
              ]"
                        >
                            <component
                                :is="item.icon"
                                :class="[
                  isActiveRoute(item.href)
                    ? 'text-primary-500'
                    : 'text-gray-400 group-hover:text-gray-500',
                  'flex-shrink-0 mr-3 h-5 w-5 transition-colors'
                ]"
                            />
                            {{ item.name }}
                            <span
                                v-if="item.badge"
                                class="ml-auto inline-block py-0.5 px-2 text-xs font-medium rounded-full"
                                :class="item.badgeClass"
                            >
                {{ item.badge }}
              </span>
                        </router-link>
                    </div>

                    <!-- Admin section -->
                    <div v-if="isAdmin" class="pt-8">
                        <h3 class="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                            Administration
                        </h3>
                        <div class="mt-3 space-y-1">
                            <router-link
                                v-for="item in adminNavigation"
                                :key="item.name"
                                :to="item.href"
                                :class="[
                  isActiveRoute(item.href)
                    ? 'bg-primary-50 border-primary-500 text-primary-700'
                    : 'border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                  'group flex items-center px-3 py-2 text-sm font-medium border-l-4 transition-colors'
                ]"
                            >
                                <component
                                    :is="item.icon"
                                    :class="[
                    isActiveRoute(item.href)
                      ? 'text-primary-500'
                      : 'text-gray-400 group-hover:text-gray-500',
                    'flex-shrink-0 mr-3 h-5 w-5 transition-colors'
                  ]"
                                />
                                {{ item.name }}
                            </router-link>
                        </div>
                    </div>

                    <!-- Developer tools (Admin only) -->
                    <div v-if="isAdmin" class="pt-6">
                        <h3 class="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                            Developer Tools
                        </h3>
                        <div class="mt-3 space-y-1">
                            <router-link
                                v-for="item in developerNavigation"
                                :key="item.name"
                                :to="item.href"
                                :class="[
                  isActiveRoute(item.href)
                    ? 'bg-primary-50 border-primary-500 text-primary-700'
                    : 'border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                  'group flex items-center px-3 py-2 text-sm font-medium border-l-4 transition-colors'
                ]"
                            >
                                <component
                                    :is="item.icon"
                                    :class="[
                    isActiveRoute(item.href)
                      ? 'text-primary-500'
                      : 'text-gray-400 group-hover:text-gray-500',
                    'flex-shrink-0 mr-3 h-5 w-5 transition-colors'
                  ]"
                                />
                                {{ item.name }}
                            </router-link>
                        </div>
                    </div>

                </nav>

                <!-- System status -->
                <div class="flex-shrink-0 px-3 pb-4">
                    <div class="bg-gray-50 rounded-lg p-4">
                        <div class="flex items-center">
                            <div :class="systemStatus.color" class="flex-shrink-0 w-3 h-3 rounded-full"></div>
                            <div class="ml-3 min-w-0 flex-1">
                                <p class="text-sm font-medium text-gray-900">
                                    {{ systemStatus.text }}
                                </p>
                                <p class="text-xs text-gray-500">
                                    {{ modemsOnline }}/{{ totalModems }} modems online
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {computed, ref, onMounted, onUnmounted} from 'vue'
import {useRoute} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import {useSystemStore} from '@/stores/system'

// Icons
import {
    HomeIcon,
    ServerIcon,
    ChartBarIcon,
    DocumentTextIcon,
    CogIcon,
    UsersIcon,
    WifiIcon,
    BugAntIcon
} from '@heroicons/vue/24/outline'

const route = useRoute()
const authStore = useAuthStore()
const systemStore = useSystemStore()

// Computed properties
const isAdmin = computed(() => authStore.isAdmin)
const systemStatus = computed(() => systemStore.systemStatus)
const totalModems = computed(() => systemStore.totalModems)
const modemsOnline = computed(() => systemStore.onlineModems)

// Navigation items
const navigation = [
    {name: 'Dashboard', href: '/dashboard', icon: HomeIcon},
    {name: 'Индивидуальные прокси', href: '/dedicated-proxies', icon: 'NetworkIcon', adminOnly: true},
    {name: 'Modems', href: '/modems', icon: ServerIcon},
    {name: 'Statistics', href: '/statistics', icon: ChartBarIcon},
    {name: 'Logs', href: '/logs', icon: DocumentTextIcon}
]

const adminNavigation = [
    {name: 'Settings', href: '/settings', icon: CogIcon},
    {name: 'Users', href: '/users', icon: UsersIcon}
]

const developerNavigation = [
    {name: 'Отладка устройств', href: '/device-debug', icon: BugAntIcon}
]

// Methods
const isActiveRoute = (href) => {
    return route.path.startsWith(href)
}

// Auto-refresh system status
let statusInterval = null

onMounted(() => {
    systemStore.fetchSystemStatus()
    statusInterval = setInterval(() => {
        systemStore.fetchSystemStatus()
    }, 30000) // Refresh every 30 seconds
})

onUnmounted(() => {
    if (statusInterval) {
        clearInterval(statusInterval)
    }
})
</script>
