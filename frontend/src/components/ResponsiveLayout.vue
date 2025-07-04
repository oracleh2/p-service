<template>
    <div class="min-h-screen bg-gray-50">
        <!-- Mobile menu overlay -->
        <div v-if="isMobileMenuOpen" class="lg:hidden">
            <div class="fixed inset-0 z-50 flex">
                <!-- Overlay -->
                <div class="fixed inset-0 bg-gray-600 bg-opacity-75" @click="toggleMobileMenu"></div>

                <!-- Mobile sidebar -->
                <div class="relative flex w-full max-w-xs flex-1 flex-col bg-white">
                    <div class="absolute top-0 right-0 -mr-12 pt-2">
                        <button
                            @click="toggleMobileMenu"
                            class="ml-1 flex h-10 w-10 items-center justify-center rounded-full focus:outline-none focus:ring-2 focus:ring-inset focus:ring-white"
                        >
                            <XMarkIcon class="h-6 w-6 text-white"/>
                        </button>
                    </div>

                    <AppSidebar :is-mobile="true" @close="toggleMobileMenu"/>
                </div>
            </div>
        </div>

        <!-- Desktop layout -->
        <div class="flex h-screen overflow-hidden">
            <!-- Desktop sidebar -->
            <AppSidebar
                class="hidden lg:flex"
                :class="sidebarClasses"
            />

            <!-- Main content area -->
            <div class="flex flex-1 flex-col overflow-hidden">
                <!-- Top navigation bar -->
                <header
                    class="w-full border-b border-gray-200 bg-white shadow-sm"
                    :class="headerClasses"
                >
                    <div class="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
                        <!-- Mobile menu button -->
                        <button
                            @click="toggleMobileMenu"
                            class="lg:hidden -ml-0.5 -mt-0.5 h-12 w-12 inline-flex items-center justify-center rounded-md text-gray-500 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
                        >
                            <Bars3Icon class="h-6 w-6"/>
                        </button>

                        <!-- Page title for larger screens -->
                        <div class="hidden sm:block">
                            <h1 class="text-2xl font-semibold text-gray-900">
                                {{ pageTitle }}
                            </h1>
                        </div>

                        <!-- Right side actions -->
                        <div class="flex items-center space-x-4">
                            <!-- Notifications -->
                            <button
                                class="p-2 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded-lg">
                                <BellIcon class="h-6 w-6"/>
                            </button>

                            <!-- Full screen toggle -->
                            <button
                                @click="toggleFullscreen"
                                class="hidden xl:block p-2 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded-lg"
                            >
                                <ArrowsPointingOutIcon v-if="!isFullscreen" class="h-6 w-6"/>
                                <ArrowsPointingInIcon v-else class="h-6 w-6"/>
                            </button>

                            <!-- User menu -->
                            <div class="relative">
                                <button
                                    @click="toggleUserMenu"
                                    class="flex items-center text-sm rounded-full focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                                >
                                    <div class="h-8 w-8 rounded-full bg-primary-600 flex items-center justify-center">
                    <span class="text-white text-sm font-medium">
                      {{ userInitials }}
                    </span>
                                    </div>
                                </button>

                                <!-- User dropdown -->
                                <div
                                    v-if="isUserMenuOpen"
                                    class="absolute right-0 z-50 mt-2 w-48 rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none"
                                >
                                    <router-link
                                        to="/settings"
                                        class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                        @click="toggleUserMenu"
                                    >
                                        Settings
                                    </router-link>
                                    <button
                                        @click="logout"
                                        class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                                    >
                                        Sign out
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </header>

                <!-- Main content -->
                <main
                    class="flex-1 overflow-auto bg-gray-50 focus:outline-none"
                    :class="mainContentClasses"
                >
                    <div
                        class="py-6"
                        :class="containerClasses"
                    >
                        <div
                            class="mx-auto px-4 sm:px-6 lg:px-8"
                            :class="contentWidthClasses"
                        >
                            <slot/>
                        </div>
                    </div>
                </main>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, computed, onMounted, onUnmounted} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import AppSidebar from '@/components/AppSidebar.vue'
import {
    Bars3Icon,
    XMarkIcon,
    BellIcon,
    ArrowsPointingOutIcon,
    ArrowsPointingInIcon
} from '@heroicons/vue/24/outline'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// Reactive state
const isMobileMenuOpen = ref(false)
const isUserMenuOpen = ref(false)
const isFullscreen = ref(false)
const screenWidth = ref(window.innerWidth)

// Computed properties
const pageTitle = computed(() => {
    return route.meta.title || 'Dashboard'
})

const userInitials = computed(() => {
    const user = authStore.user
    if (!user) return 'U'
    return (user.username || user.email || 'User')
        .split(' ')
        .map(name => name.charAt(0))
        .join('')
        .toUpperCase()
        .slice(0, 2)
})

// Responsive classes based on screen size
const sidebarClasses = computed(() => {
    const baseClasses = 'flex-shrink-0'

    // Wider sidebars for larger screens
    if (screenWidth.value >= 3840) return `${baseClasses} w-112` // 4K: 448px
    if (screenWidth.value >= 2560) return `${baseClasses} w-104` // 2K: 416px
    if (screenWidth.value >= 1920) return `${baseClasses} w-96`  // Full HD: 384px
    if (screenWidth.value >= 1536) return `${baseClasses} w-88`  // 2XL: 352px
    if (screenWidth.value >= 1280) return `${baseClasses} w-80`  // XL: 320px
    return `${baseClasses} w-72` // Default: 288px
})

const headerClasses = computed(() => {
    if (screenWidth.value >= 3840) return 'px-8' // 4K
    if (screenWidth.value >= 2560) return 'px-6' // 2K
    return '' // Default padding
})

const mainContentClasses = computed(() => {
    if (screenWidth.value >= 3840) return 'p-8' // 4K: more padding
    if (screenWidth.value >= 2560) return 'p-6' // 2K: medium padding
    return '' // Default
})

const containerClasses = computed(() => {
    if (screenWidth.value >= 3840) return 'py-8' // 4K
    if (screenWidth.value >= 2560) return 'py-8' // 2K
    return 'py-6' // Default
})

const contentWidthClasses = computed(() => {
    // Progressive max-width based on screen size
    if (screenWidth.value >= 7680) return 'max-w-24xl' // 8K
    if (screenWidth.value >= 5120) return 'max-w-20xl' // 5K
    if (screenWidth.value >= 3840) return 'max-w-16xl' // 4K
    if (screenWidth.value >= 3200) return 'max-w-15xl' // Ultra-wide
    if (screenWidth.value >= 2560) return 'max-w-14xl' // 2K
    if (screenWidth.value >= 1920) return 'max-w-12xl' // Full HD
    if (screenWidth.value >= 1536) return 'max-w-10xl' // 2XL
    if (screenWidth.value >= 1280) return 'max-w-8xl'  // XL
    return 'max-w-7xl' // Default
})

// Methods
const toggleMobileMenu = () => {
    isMobileMenuOpen.value = !isMobileMenuOpen.value
}

const toggleUserMenu = () => {
    isUserMenuOpen.value = !isUserMenuOpen.value
}

const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen()
        isFullscreen.value = true
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen()
            isFullscreen.value = false
        }
    }
}

const logout = async () => {
    await authStore.logout()
    router.push('/login')
}

const handleResize = () => {
    screenWidth.value = window.innerWidth
}

const handleFullscreenChange = () => {
    isFullscreen.value = !!document.fullscreenElement
}

const handleClickOutside = (event) => {
    // Close user menu when clicking outside
    if (isUserMenuOpen.value) {
        const userMenu = event.target.closest('.relative')
        if (!userMenu) {
            isUserMenuOpen.value = false
        }
    }
}

// Lifecycle hooks
onMounted(() => {
    window.addEventListener('resize', handleResize)
    window.addEventListener('click', handleClickOutside)
    document.addEventListener('fullscreenchange', handleFullscreenChange)

    // Set initial screen width
    handleResize()
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    window.removeEventListener('click', handleClickOutside)
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
/* Custom scrollbar for webkit browsers */
.overflow-auto::-webkit-scrollbar {
    width: 6px;
}

.overflow-auto::-webkit-scrollbar-track {
    background: transparent;
}

.overflow-auto::-webkit-scrollbar-thumb {
    background-color: rgba(156, 163, 175, 0.5);
    border-radius: 3px;
}

.overflow-auto::-webkit-scrollbar-thumb:hover {
    background-color: rgba(107, 114, 128, 0.7);
}

/* Smooth transitions */
.flex-1 {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Focus trap for accessibility */
.focus-within\:ring-2:focus-within {
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5);
}
</style>
