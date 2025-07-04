<template>
    <div class="relative z-10 flex-shrink-0 flex h-16 bg-white border-b border-gray-200 lg:border-none">
        <!-- Mobile menu button -->
        <button
            type="button"
            class="px-4 border-r border-gray-200 text-gray-400 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500 lg:hidden"
            @click="toggleMobileMenu"
        >
            <span class="sr-only">Open sidebar</span>
            <Bars3Icon class="h-6 w-6" aria-hidden="true"/>
        </button>

        <!-- Search bar -->
        <div class="flex-1 px-4 flex justify-between sm:px-6 lg:max-w-6xl lg:mx-auto lg:px-8">
            <div class="flex-1 flex">
                <div class="w-full flex md:ml-0">
                    <label for="search-field" class="sr-only">Search</label>
                    <div class="relative w-full text-gray-400 focus-within:text-gray-600">
                        <div class="absolute inset-y-0 left-0 flex items-center pointer-events-none">
                            <MagnifyingGlassIcon class="h-5 w-5" aria-hidden="true"/>
                        </div>
                        <input
                            id="search-field"
                            v-model="searchQuery"
                            class="block w-full h-full pl-8 pr-3 py-2 border-transparent text-gray-900 placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-0 focus:border-transparent"
                            placeholder="Search modems, IPs, logs..."
                            type="search"
                            @keyup.enter="performSearch"
                        />
                    </div>
                </div>
            </div>

            <!-- Right section -->
            <div class="ml-4 flex items-center md:ml-6">
                <!-- Quick actions -->
                <div class="hidden xl:flex xl:items-center xl:space-x-2 xl:mr-4">
                    <button
                        type="button"
                        class="btn btn-sm btn-secondary"
                        @click="rotateAllModems"
                        :disabled="isRotating"
                    >
                        <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isRotating }"/>
                        Rotate All
                    </button>
                </div>

                <!-- Notifications -->
                <div class="relative">
                    <button
                        type="button"
                        class="bg-white p-1 rounded-full text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                        @click="showNotifications = !showNotifications"
                    >
                        <span class="sr-only">View notifications</span>
                        <BellIcon class="h-6 w-6" aria-hidden="true"/>
                        <span
                            v-if="unreadNotifications > 0"
                            class="absolute -top-1 -right-1 h-4 w-4 bg-red-500 text-white text-xs rounded-full flex-center"
                        >
              {{ unreadNotifications > 99 ? '99+' : unreadNotifications }}
            </span>
                    </button>

                    <!-- Notifications dropdown -->
                    <transition
                        enter-active-class="transition ease-out duration-200"
                        enter-from-class="transform opacity-0 scale-95"
                        enter-to-class="transform opacity-100 scale-100"
                        leave-active-class="transition ease-in duration-75"
                        leave-from-class="transform opacity-100 scale-100"
                        leave-to-class="transform opacity-0 scale-95"
                    >
                        <div
                            v-if="showNotifications"
                            class="origin-top-right absolute right-0 mt-2 w-96 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 focus:outline-none"
                            @click.stop
                        >
                            <div class="py-1">
                                <div class="px-4 py-2 text-sm text-gray-700 border-b border-gray-200 flex-between">
                                    <span class="font-medium">Notifications</span>
                                    <button
                                        v-if="unreadNotifications > 0"
                                        @click="markAllAsRead"
                                        class="text-primary-600 hover:text-primary-700 text-xs"
                                    >
                                        Mark all as read
                                    </button>
                                </div>

                                <div class="max-h-96 overflow-y-auto">
                                    <div
                                        v-for="notification in notifications"
                                        :key="notification.id"
                                        :class="[
                      'px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100',
                      !notification.read ? 'bg-blue-50' : ''
                    ]"
                                        @click="markAsRead(notification.id)"
                                    >
                                        <div class="flex">
                                            <div class="flex-shrink-0">
                                                <component
                                                    :is="getNotificationIcon(notification.type)"
                                                    :class="[
                            'h-5 w-5',
                            getNotificationColor(notification.type)
                          ]"
                                                />
                                            </div>
                                            <div class="ml-3 flex-1">
                                                <p class="text-sm font-medium text-gray-900">
                                                    {{ notification.title }}
                                                </p>
                                                <p class="text-sm text-gray-500">
                                                    {{ notification.message }}
                                                </p>
                                                <p class="text-xs text-gray-400 mt-1">
                                                    {{ formatTime(notification.timestamp) }}
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    <div
                                        v-if="notifications.length === 0"
                                        class="px-4 py-8 text-center text-gray-500"
                                    >
                                        No notifications
                                    </div>
                                </div>
                            </div>
                        </div>
                    </transition>
                </div>

                <!-- Profile dropdown -->
                <div class="ml-3 relative">
                    <div>
                        <button
                            type="button"
                            class="max-w-xs bg-white rounded-full flex items-center text-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                            @click="showProfileMenu = !showProfileMenu"
                        >
                            <span class="sr-only">Open user menu</span>
                            <div class="h-8 w-8 rounded-full bg-primary-100 flex-center">
                                <UserIcon class="h-5 w-5 text-primary-600"/>
                            </div>
                            <span class="ml-3 text-gray-700 text-sm font-medium hidden lg:block">
                {{ userInfo.username }}
              </span>
                            <ChevronDownIcon class="ml-1 h-5 w-5 text-gray-400 hidden lg:block"/>
                        </button>
                    </div>

                    <!-- Profile dropdown menu -->
                    <transition
                        enter-active-class="transition ease-out duration-200"
                        enter-from-class="transform opacity-0 scale-95"
                        enter-to-class="transform opacity-100 scale-100"
                        leave-active-class="transition ease-in duration-75"
                        leave-from-class="transform opacity-100 scale-100"
                        leave-to-class="transform opacity-0 scale-95"
                    >
                        <div
                            v-if="showProfileMenu"
                            class="origin-top-right absolute right-0 mt-2 w-48 rounded-md shadow-lg bg-white ring-1 ring-black ring-opacity-5 focus:outline-none"
                            @click.stop
                        >
                            <div class="py-1">
                                <div class="px-4 py-2 text-sm text-gray-700 border-b border-gray-200">
                                    <p class="font-medium">{{ userInfo.username }}</p>
                                    <p class="text-gray-500">{{ userInfo.role }}</p>
                                </div>

                                <button
                                    v-for="item in profileMenuItems"
                                    :key="item.name"
                                    @click="item.action"
                                    class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                >
                                    <component :is="item.icon" class="h-4 w-4 mr-2 inline"/>
                                    {{ item.name }}
                                </button>
                            </div>
                        </div>
                    </transition>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, computed, onMounted, onUnmounted} from 'vue'
import {useRouter} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import {useNotificationStore} from '@/stores/notifications'
import {format} from 'date-fns'
import {useToast} from 'vue-toastification'
import api from '@/utils/api'

// Icons
import {
    Bars3Icon,
    MagnifyingGlassIcon,
    BellIcon,
    UserIcon,
    ChevronDownIcon,
    ArrowPathIcon,
    CogIcon,
    KeyIcon,
    ArrowRightOnRectangleIcon,
    ExclamationTriangleIcon,
    CheckCircleIcon,
    InformationCircleIcon,
    XCircleIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const toast = useToast()

// State
const searchQuery = ref('')
const showNotifications = ref(false)
const showProfileMenu = ref(false)
const isRotating = ref(false)

// Computed
const userInfo = computed(() => authStore.userInfo)
const notifications = computed(() => notificationStore.notifications)
const unreadNotifications = computed(() => notificationStore.unreadCount)

// Profile menu items
const profileMenuItems = [
    {
        name: 'Settings',
        icon: CogIcon,
        action: () => {
            showProfileMenu.value = false
            router.push('/settings')
        }
    },
    {
        name: 'Change Password',
        icon: KeyIcon,
        action: () => {
            showProfileMenu.value = false
            // TODO: Open change password modal
        }
    },
    {
        name: 'Sign Out',
        icon: ArrowRightOnRectangleIcon,
        action: async () => {
            showProfileMenu.value = false
            await authStore.logout()
            router.push('/login')
        }
    }
]

// Methods
const toggleMobileMenu = () => {
    // TODO: Implement mobile menu toggle
    console.log('Toggle mobile menu')
}

const performSearch = () => {
    if (searchQuery.value.trim()) {
        // TODO: Implement search functionality
        console.log('Search:', searchQuery.value)
    }
}

const rotateAllModems = async () => {
    try {
        isRotating.value = true
        const response = await api.post('/admin/modems/rotate-all')

        toast.success(response.data.message || 'All modems rotation initiated')

        // Refresh notifications
        await notificationStore.fetchNotifications()
    } catch (error) {
        toast.error('Failed to rotate modems')
    } finally {
        isRotating.value = false
    }
}

const markAsRead = async (notificationId) => {
    await notificationStore.markAsRead(notificationId)
}

const markAllAsRead = async () => {
    await notificationStore.markAllAsRead()
}

const getNotificationIcon = (type) => {
    switch (type) {
        case 'error':
            return XCircleIcon
        case 'warning':
            return ExclamationTriangleIcon
        case 'success':
            return CheckCircleIcon
        case 'info':
        default:
            return InformationCircleIcon
    }
}

const getNotificationColor = (type) => {
    switch (type) {
        case 'error':
            return 'text-red-500'
        case 'warning':
            return 'text-yellow-500'
        case 'success':
            return 'text-green-500'
        case 'info':
        default:
            return 'text-blue-500'
    }
}

const formatTime = (timestamp) => {
    return format(new Date(timestamp), 'MMM d, HH:mm')
}

// Close dropdowns when clicking outside
const handleClickOutside = (event) => {
    if (!event.target.closest('.relative')) {
        showNotifications.value = false
        showProfileMenu.value = false
    }
}

// Lifecycle
onMounted(() => {
    document.addEventListener('click', handleClickOutside)

    // Fetch initial notifications
    notificationStore.fetchNotifications()

    // Set up notification polling
    notificationStore.startPolling()
})

onUnmounted(() => {
    document.removeEventListener('click', handleClickOutside)
    notificationStore.stopPolling()
})
</script>
