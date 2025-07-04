import axios from 'axios'
import {useToast} from 'vue-toastification'

const toast = useToast()

// Create axios instance
const api = axios.create({
    baseURL: '/api/v1',
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json'
    }
})

// Request interceptor
api.interceptors.request.use(
    (config) => {
        // Add timestamp to prevent caching
        config.params = {
            ...config.params,
            _t: Date.now()
        }

        return config
    },
    (error) => {
        return Promise.reject(error)
    }
)

// Response interceptor
api.interceptors.response.use(
    (response) => {
        return response
    },
    (error) => {
        const {response} = error

        if (response) {
            const {status, data} = response

            switch (status) {
                case 400:
                    toast.error(data.detail || 'Bad request')
                    break
                case 401:
                    toast.error('Unauthorized access')
                    // Redirect to login
                    if (window.location.pathname !== '/login') {
                        localStorage.removeItem('token')
                        localStorage.removeItem('user')
                        window.location.href = '/login'
                    }
                    break
                case 403:
                    toast.error('Access forbidden')
                    break
                case 404:
                    toast.error('Resource not found')
                    break
                case 422:
                    if (data.detail && Array.isArray(data.detail)) {
                        data.detail.forEach(err => {
                            toast.error(`${err.loc?.join(' -> ')}: ${err.msg}`)
                        })
                    } else {
                        toast.error(data.detail || 'Validation error')
                    }
                    break
                case 500:
                    toast.error('Internal server error')
                    break
                case 503:
                    toast.error('Service unavailable')
                    break
                default:
                    toast.error(data.detail || 'An error occurred')
            }
        } else if (error.request) {
            toast.error('Network error - please check your connection')
        } else {
            toast.error('Request failed')
        }

        return Promise.reject(error)
    }
)

export default api
