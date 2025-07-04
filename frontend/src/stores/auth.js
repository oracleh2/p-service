import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import api from '@/utils/api'

export const useAuthStore = defineStore('auth', () => {
    // State
    const token = ref(localStorage.getItem('token') || '')
    const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
    const isLoading = ref(false)
    const error = ref('')

    // Getters
    const isAuthenticated = computed(() => !!token.value && !!user.value)
    const isAdmin = computed(() => user.value?.role === 'admin')
    const userInfo = computed(() => user.value)

    // Actions
    const login = async (credentials) => {
        try {
            isLoading.value = true
            error.value = ''

            const response = await api.post('/auth/login', credentials)
            const {access_token, token_type, user_id, username, role, api_key} = response.data

            // Store token and user info
            token.value = access_token
            user.value = {
                id: user_id,
                username,
                role,
                api_key
            }

            // Save to localStorage
            localStorage.setItem('token', access_token)
            localStorage.setItem('user', JSON.stringify(user.value))

            // Set default auth header
            api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`

            return true
        } catch (err) {
            error.value = err.response?.data?.detail || 'Login failed'
            return false
        } finally {
            isLoading.value = false
        }
    }

    const logout = async () => {
        try {
            // Clear state
            token.value = ''
            user.value = null
            error.value = ''

            // Clear localStorage
            localStorage.removeItem('token')
            localStorage.removeItem('user')

            // Remove auth header
            delete api.defaults.headers.common['Authorization']

            return true
        } catch (err) {
            console.error('Logout error:', err)
            return false
        }
    }

    const restoreAuth = async () => {
        try {
            const savedToken = localStorage.getItem('token')
            const savedUser = localStorage.getItem('user')

            if (savedToken && savedUser) {
                token.value = savedToken
                user.value = JSON.parse(savedUser)

                // Set auth header
                api.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`

                // Verify token by fetching user info
                const response = await api.get('/auth/me')

                // Update user info
                user.value = {
                    id: response.data.id,
                    username: response.data.username,
                    role: response.data.role,
                    api_key: response.data.api_key
                }

                localStorage.setItem('user', JSON.stringify(user.value))

                return true
            }

            return false
        } catch (err) {
            console.error('Auth restore failed:', err)
            // Clear invalid auth
            await logout()
            return false
        }
    }

    const refreshApiKey = async () => {
        try {
            isLoading.value = true
            error.value = ''

            const response = await api.post('/auth/refresh-api-key')

            if (user.value) {
                user.value.api_key = response.data.api_key
                localStorage.setItem('user', JSON.stringify(user.value))
            }

            return response.data.api_key
        } catch (err) {
            error.value = err.response?.data?.detail || 'Failed to refresh API key'
            throw err
        } finally {
            isLoading.value = false
        }
    }

    const changePassword = async (oldPassword, newPassword) => {
        try {
            isLoading.value = true
            error.value = ''

            await api.post('/auth/change-password', {
                old_password: oldPassword,
                new_password: newPassword
            })

            return true
        } catch (err) {
            error.value = err.response?.data?.detail || 'Failed to change password'
            throw err
        } finally {
            isLoading.value = false
        }
    }

    const clearError = () => {
        error.value = ''
    }

    // Initialize auth on store creation
    if (token.value) {
        api.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
    }

    return {
        // State
        token,
        user,
        isLoading,
        error,

        // Getters
        isAuthenticated,
        isAdmin,
        userInfo,

        // Actions
        login,
        logout,
        restoreAuth,
        refreshApiKey,
        changePassword,
        clearError
    }
})
