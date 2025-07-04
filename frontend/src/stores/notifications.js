import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import api from '@/utils/api'

export const useNotificationStore = defineStore('notifications', () => {
    // State
    const notifications = ref([])
    const isLoading = ref(false)
    const pollingInterval = ref(null)

    // Getters
    const unreadCount = computed(() =>
        notifications.value.filter(n => !n.read).length
    )

    const recentNotifications = computed(() =>
        notifications.value.slice(0, 10)
    )

    // Actions
    const fetchNotifications = async () => {
        try {
            isLoading.value = true

            // Mock notifications for now
            // TODO: Replace with real API call when backend implements notifications
            const mockNotifications = [
                {
                    id: '1',
                    type: 'warning',
                    title: 'Modem Offline',
                    message: 'Android device android_ABC123 has been offline for 5 minutes',
                    timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
                    read: false
                },
                {
                    id: '2',
                    type: 'success',
                    title: 'IP Rotation Complete',
                    message: 'Successfully rotated IP for 3 modems',
                    timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
                    read: false
                },
                {
                    id: '3',
                    type: 'error',
                    title: 'Low Success Rate',
                    message: 'USB modem usb_0 has success rate below 85%',
                    timestamp: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
                    read: true
                },
                {
                    id: '4',
                    type: 'info',
                    title: 'System Update',
                    message: 'Rotation interval updated to 8 minutes',
                    timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
                    read: true
                }
            ]

            notifications.value = mockNotifications

        } catch (error) {
            console.error('Failed to fetch notifications:', error)
        } finally {
            isLoading.value = false
        }
    }

    const markAsRead = async (notificationId) => {
        try {
            // Find and mark notification as read
            const notification = notifications.value.find(n => n.id === notificationId)
            if (notification) {
                notification.read = true
            }

            // TODO: API call to mark as read
            // await api.patch(`/notifications/${notificationId}/read`)

        } catch (error) {
            console.error('Failed to mark notification as read:', error)
        }
    }

    const markAllAsRead = async () => {
        try {
            // Mark all notifications as read
            notifications.value.forEach(notification => {
                notification.read = true
            })

            // TODO: API call to mark all as read
            // await api.post('/notifications/mark-all-read')

        } catch (error) {
            console.error('Failed to mark all notifications as read:', error)
        }
    }

    const addNotification = (notification) => {
        const newNotification = {
            id: Date.now().toString(),
            timestamp: new Date().toISOString(),
            read: false,
            ...notification
        }

        notifications.value.unshift(newNotification)

        // Keep only last 50 notifications
        if (notifications.value.length > 50) {
            notifications.value = notifications.value.slice(0, 50)
        }
    }

    const removeNotification = (notificationId) => {
        const index = notifications.value.findIndex(n => n.id === notificationId)
        if (index > -1) {
            notifications.value.splice(index, 1)
        }
    }

    const clearAllNotifications = () => {
        notifications.value = []
    }

    const startPolling = () => {
        if (pollingInterval.value) {
            clearInterval(pollingInterval.value)
        }

        // Poll for new notifications every 30 seconds
        pollingInterval.value = setInterval(() => {
            fetchNotifications()
        }, 30000)
    }

    const stopPolling = () => {
        if (pollingInterval.value) {
            clearInterval(pollingInterval.value)
            pollingInterval.value = null
        }
    }

    // Simulate real-time notifications
    const simulateNotification = (type = 'info') => {
        const messages = {
            info: {
                title: 'System Info',
                message: 'This is a test notification'
            },
            success: {
                title: 'Operation Successful',
                message: 'The operation completed successfully'
            },
            warning: {
                title: 'Warning',
                message: 'Please check system status'
            },
            error: {
                title: 'Error Occurred',
                message: 'An error occurred in the system'
            }
        }

        addNotification({
            type,
            ...messages[type]
        })
    }

    return {
        // State
        notifications,
        isLoading,

        // Getters
        unreadCount,
        recentNotifications,

        // Actions
        fetchNotifications,
        markAsRead,
        markAllAsRead,
        addNotification,
        removeNotification,
        clearAllNotifications,
        startPolling,
        stopPolling,
        simulateNotification
    }
})
