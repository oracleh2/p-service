<template>
    <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
        <div class="max-w-md w-full space-y-8">
            <div>
                <div class="mx-auto h-12 w-12 bg-primary-600 rounded-xl flex-center">
                    <WifiIcon class="h-8 w-8 text-white"/>
                </div>
                <h2 class="mt-6 text-center text-3xl font-extrabold text-gray-900">
                    Mobile Proxy Admin
                </h2>
                <p class="mt-2 text-center text-sm text-gray-600">
                    Sign in to manage your mobile proxy infrastructure
                </p>
            </div>

            <form class="mt-8 space-y-6" @submit.prevent="handleLogin">
                <div class="rounded-md shadow-sm space-y-4">
                    <div>
                        <label for="username" class="form-label">Username</label>
                        <input
                            id="username"
                            v-model="form.username"
                            type="text"
                            required
                            class="form-input"
                            :class="{ 'border-red-300': errors.username }"
                            placeholder="Enter your username"
                        />
                        <p v-if="errors.username" class="form-error">{{ errors.username }}</p>
                    </div>

                    <div>
                        <label for="password" class="form-label">Password</label>
                        <div class="relative">
                            <input
                                id="password"
                                v-model="form.password"
                                :type="showPassword ? 'text' : 'password'"
                                required
                                class="form-input pr-10"
                                :class="{ 'border-red-300': errors.password }"
                                placeholder="Enter your password"
                            />
                            <button
                                type="button"
                                class="absolute inset-y-0 right-0 pr-3 flex items-center"
                                @click="showPassword = !showPassword"
                            >
                                <EyeIcon v-if="!showPassword" class="h-5 w-5 text-gray-400"/>
                                <EyeSlashIcon v-else class="h-5 w-5 text-gray-400"/>
                            </button>
                        </div>
                        <p v-if="errors.password" class="form-error">{{ errors.password }}</p>
                    </div>
                </div>

                <div class="flex items-center justify-between">
                    <div class="flex items-center">
                        <input
                            id="remember-me"
                            v-model="form.rememberMe"
                            name="remember-me"
                            type="checkbox"
                            class="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <label for="remember-me" class="ml-2 block text-sm text-gray-900">
                            Remember me
                        </label>
                    </div>

                    <div class="text-sm">
                        <a href="#" class="font-medium text-primary-600 hover:text-primary-500">
                            Forgot your password?
                        </a>
                    </div>
                </div>

                <div>
                    <button
                        type="submit"
                        :disabled="isLoading"
                        class="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
            <span class="absolute left-0 inset-y-0 flex items-center pl-3">
              <LockClosedIcon class="h-5 w-5 text-primary-500 group-hover:text-primary-400"/>
            </span>
                        <span v-if="isLoading" class="flex items-center">
              <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none"
                   viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Signing in...
            </span>
                        <span v-else>Sign in</span>
                    </button>
                </div>

                <!-- Error message -->
                <div v-if="error" class="rounded-md bg-red-50 p-4">
                    <div class="flex">
                        <ExclamationTriangleIcon class="h-5 w-5 text-red-400"/>
                        <div class="ml-3">
                            <h3 class="text-sm font-medium text-red-800">
                                Sign in failed
                            </h3>
                            <div class="mt-2 text-sm text-red-700">
                                {{ error }}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Demo credentials -->
                <div class="rounded-md bg-blue-50 p-4">
                    <div class="flex">
                        <InformationCircleIcon class="h-5 w-5 text-blue-400"/>
                        <div class="ml-3">
                            <h3 class="text-sm font-medium text-blue-800">
                                Demo Credentials
                            </h3>
                            <div class="mt-2 text-sm text-blue-700">
                                <p><strong>Username:</strong> admin</p>
                                <p><strong>Password:</strong> admin123</p>
                            </div>
                        </div>
                    </div>
                </div>
            </form>
        </div>
    </div>
</template>

<script setup>
import {ref, reactive, computed} from 'vue'
import {useRouter} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import {useToast} from 'vue-toastification'

// Icons
import {
    WifiIcon,
    EyeIcon,
    EyeSlashIcon,
    LockClosedIcon,
    ExclamationTriangleIcon,
    InformationCircleIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

// State
const showPassword = ref(false)
const form = reactive({
    username: '',
    password: '',
    rememberMe: false
})

const errors = ref({
    username: '',
    password: ''
})

// Computed
const isLoading = computed(() => authStore.isLoading)
const error = computed(() => authStore.error)

// Methods
const validateForm = () => {
    errors.value = {
        username: '',
        password: ''
    }

    let isValid = true

    if (!form.username.trim()) {
        errors.value.username = 'Username is required'
        isValid = false
    } else if (form.username.length < 3) {
        errors.value.username = 'Username must be at least 3 characters'
        isValid = false
    }

    if (!form.password.trim()) {
        errors.value.password = 'Password is required'
        isValid = false
    } else if (form.password.length < 6) {
        errors.value.password = 'Password must be at least 6 characters'
        isValid = false
    }

    return isValid
}

const handleLogin = async () => {
    // Clear previous errors
    authStore.clearError()

    // Validate form
    if (!validateForm()) {
        return
    }

    try {
        const success = await authStore.login({
            username: form.username,
            password: form.password
        })

        if (success) {
            toast.success('Successfully signed in!')
            router.push('/dashboard')
        }
    } catch (error) {
        console.error('Login error:', error)
    }
}

// Auto-fill demo credentials
const fillDemoCredentials = () => {
    form.username = 'admin'
    form.password = 'admin123'
}

// Initialize with demo credentials for development
// if (import.meta.env.MODE === 'development') {
    fillDemoCredentials()
// }
</script>

<style scoped>
/* Custom styles for login page */
.form-input:focus {
    border-color: rgb(59 130 246);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
</style>
