<!-- frontend/src/views/Users.vue -->
<template>
    <div class="space-y-6">
        <!-- Header -->
        <div class="sm:flex sm:items-center sm:justify-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">User Management</h1>
                <p class="mt-2 text-sm text-gray-700">
                    Manage user accounts, permissions, and API access
                </p>
            </div>
            <div class="mt-4 sm:mt-0 sm:ml-16 sm:flex-none">
                <button
                    @click="openCreateUserModal"
                    class="btn btn-primary btn-sm"
                >
                    <UserPlusIcon class="h-4 w-4 mr-2"/>
                    Add User
                </button>
            </div>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <UsersIcon class="h-6 w-6 text-gray-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Total Users</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.totalUsers }}</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <CheckCircleIcon class="h-6 w-6 text-green-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Active Users</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.activeUsers }}</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <ShieldCheckIcon class="h-6 w-6 text-blue-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Admin Users</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.adminUsers }}</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <KeyIcon class="h-6 w-6 text-purple-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">API Keys</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.apiKeys }}</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Filters -->
        <div class="bg-white shadow rounded-lg p-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <!-- Search -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Search Users</label>
                    <input
                        v-model="filters.search"
                        @input="debounceSearch"
                        type="text"
                        placeholder="Search by username or email..."
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                </div>

                <!-- Role Filter -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Role</label>
                    <select
                        v-model="filters.role"
                        @change="fetchUsers"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                        <option value="">All Roles</option>
                        <option value="admin">Admin</option>
                        <option value="user">User</option>
                    </select>
                </div>

                <!-- Status Filter -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Status</label>
                    <select
                        v-model="filters.status"
                        @change="fetchUsers"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                        <option value="">All Status</option>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Users Table -->
        <div class="bg-white shadow overflow-hidden sm:rounded-md">
            <div class="px-4 py-5 sm:p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg leading-6 font-medium text-gray-900">
                        Users ({{ totalUsers }})
                    </h3>
                </div>

                <!-- Loading State -->
                <div v-if="isLoading" class="flex justify-center py-8">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                </div>

                <!-- Empty State -->
                <div v-else-if="!users.length" class="text-center py-8">
                    <UsersIcon class="mx-auto h-12 w-12 text-gray-400"/>
                    <h3 class="mt-2 text-sm font-medium text-gray-900">No users found</h3>
                    <p class="mt-1 text-sm text-gray-500">
                        Get started by creating a new user account.
                    </p>
                    <div class="mt-6">
                        <button
                            @click="openCreateUserModal"
                            class="btn btn-primary"
                        >
                            <UserPlusIcon class="h-4 w-4 mr-2"/>
                            Add User
                        </button>
                    </div>
                </div>

                <!-- Users Table -->
                <div v-else class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                User
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Role
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Requests Usage
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Last Login
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Created
                            </th>
                            <th class="relative px-6 py-3">
                                <span class="sr-only">Actions</span>
                            </th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr
                            v-for="user in users"
                            :key="user.id"
                            class="hover:bg-gray-50"
                        >
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="flex items-center">
                                    <div class="flex-shrink-0 h-10 w-10">
                                        <div
                                            class="h-10 w-10 rounded-full bg-primary-600 flex items-center justify-center">
                        <span class="text-white text-sm font-medium">
                          {{ getUserInitials(user) }}
                        </span>
                                        </div>
                                    </div>
                                    <div class="ml-4">
                                        <div class="text-sm font-medium text-gray-900">{{ user.username }}</div>
                                        <div class="text-sm text-gray-500">{{ user.email }}</div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="getRoleClass(user.role)" class="px-2 py-1 text-xs font-medium rounded-full">
                    {{ user.role }}
                  </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="getStatusClass(user.is_active)" class="px-2 py-1 text-xs font-medium rounded-full">
                    {{ user.is_active ? 'Active' : 'Inactive' }}
                  </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                <div class="flex flex-col">
                                    <span>{{
                                            user.requests_used?.toLocaleString() || 0
                                        }} / {{ user.requests_limit?.toLocaleString() || 0 }}</span>
                                    <div class="w-full bg-gray-200 rounded-full h-2 mt-1">
                                        <div
                                            class="bg-primary-600 h-2 rounded-full"
                                            :style="{ width: getUsagePercentage(user) + '%' }"
                                        ></div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ user.last_login ? formatDate(user.last_login) : 'Never' }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ formatDate(user.created_at) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <div class="flex items-center space-x-2">
                                    <button
                                        @click="editUser(user)"
                                        class="text-primary-600 hover:text-primary-900"
                                    >
                                        <PencilIcon class="h-4 w-4"/>
                                    </button>
                                    <button
                                        @click="toggleUserStatus(user)"
                                        :class="user.is_active ? 'text-red-600 hover:text-red-900' : 'text-green-600 hover:text-green-900'"
                                    >
                                        {{ user.is_active ? 'Deactivate' : 'Activate' }}
                                    </button>
                                    <button
                                        @click="deleteUser(user)"
                                        class="text-red-600 hover:text-red-900"
                                    >
                                        <TrashIcon class="h-4 w-4"/>
                                    </button>
                                </div>
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Pagination -->
                <div class="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
                    <div class="flex-1 flex justify-between sm:hidden">
                        <button
                            @click="previousPage"
                            :disabled="pagination.offset === 0"
                            class="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                            Previous
                        </button>
                        <button
                            @click="nextPage"
                            :disabled="pagination.offset + pagination.limit >= totalUsers"
                            class="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                            Next
                        </button>
                    </div>
                    <div class="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                        <div>
                            <p class="text-sm text-gray-700">
                                Showing
                                <span class="font-medium">{{ pagination.offset + 1 }}</span>
                                to
                                <span class="font-medium">{{
                                        Math.min(pagination.offset + pagination.limit, totalUsers)
                                    }}</span>
                                of
                                <span class="font-medium">{{ totalUsers }}</span>
                                results
                            </p>
                        </div>
                        <div>
                            <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
                                <button
                                    @click="previousPage"
                                    :disabled="pagination.offset === 0"
                                    class="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                    <ChevronLeftIcon class="h-5 w-5"/>
                                </button>
                                <button
                                    @click="nextPage"
                                    :disabled="pagination.offset + pagination.limit >= totalUsers"
                                    class="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                    <ChevronRightIcon class="h-5 w-5"/>
                                </button>
                            </nav>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Create/Edit User Modal -->
        <div v-if="showUserModal" class="fixed inset-0 z-50 overflow-y-auto">
            <div class="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" @click="closeUserModal"></div>

                <div
                    class="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
                    <form @submit.prevent="saveUser">
                        <div class="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                            <div class="sm:flex sm:items-start">
                                <div class="mt-3 text-center sm:mt-0 sm:text-left w-full">
                                    <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4">
                                        {{ editingUser ? 'Edit User' : 'Create New User' }}
                                    </h3>

                                    <div class="space-y-4">
                                        <!-- Username -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700">Username</label>
                                            <input
                                                v-model="userForm.username"
                                                type="text"
                                                required
                                                class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                            >
                                        </div>

                                        <!-- Email -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700">Email</label>
                                            <input
                                                v-model="userForm.email"
                                                type="email"
                                                required
                                                class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                            >
                                        </div>

                                        <!-- Password -->
                                        <div v-if="!editingUser">
                                            <label class="block text-sm font-medium text-gray-700">Password</label>
                                            <input
                                                v-model="userForm.password"
                                                type="password"
                                                required
                                                class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                            >
                                        </div>

                                        <!-- Role -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700">Role</label>
                                            <select
                                                v-model="userForm.role"
                                                class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                            >
                                                <option value="user">User</option>
                                                <option value="admin">Admin</option>
                                            </select>
                                        </div>

                                        <!-- Requests Limit -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700">Requests
                                                Limit</label>
                                            <input
                                                v-model.number="userForm.requests_limit"
                                                type="number"
                                                min="0"
                                                class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                            >
                                        </div>

                                        <!-- Active Status -->
                                        <div>
                                            <label class="flex items-center">
                                                <input
                                                    v-model="userForm.is_active"
                                                    type="checkbox"
                                                    class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                                >
                                                <span class="ml-2 text-sm font-medium text-gray-700">
                          Active User
                        </span>
                                            </label>
                                        </div>

                                        <!-- Generate API Key -->
                                        <div v-if="editingUser">
                                            <label class="flex items-center">
                                                <input
                                                    v-model="userForm.generate_api_key"
                                                    type="checkbox"
                                                    class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                                                >
                                                <span class="ml-2 text-sm font-medium text-gray-700">
                          Generate New API Key
                        </span>
                                            </label>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                            <button
                                type="submit"
                                :disabled="isSaving"
                                class="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-primary-600 text-base font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:ml-3 sm:w-auto sm:text-sm"
                            >
                                {{ isSaving ? 'Saving...' : (editingUser ? 'Update' : 'Create') }}
                            </button>
                            <button
                                type="button"
                                @click="closeUserModal"
                                class="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
                            >
                                Cancel
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, onMounted, computed} from 'vue'
import {format} from 'date-fns'
import {useToast} from 'vue-toastification'
import {debounce} from 'lodash-es'
import api from '@/utils/api'

// Icons
import {
    UsersIcon,
    UserPlusIcon,
    CheckCircleIcon,
    ShieldCheckIcon,
    KeyIcon,
    PencilIcon,
    TrashIcon,
    ChevronLeftIcon,
    ChevronRightIcon
} from '@heroicons/vue/24/outline'

const toast = useToast()

// State
const isLoading = ref(false)
const isSaving = ref(false)
const users = ref([])
const totalUsers = ref(0)
const showUserModal = ref(false)
const editingUser = ref(null)

// Filters
const filters = ref({
    search: '',
    role: '',
    status: ''
})

// Pagination
const pagination = ref({
    limit: 20,
    offset: 0
})

// User Form
const userForm = ref({
    username: '',
    email: '',
    password: '',
    role: 'user',
    requests_limit: 10000,
    is_active: true,
    generate_api_key: false
})

// Stats
const stats = computed(() => {
    const totalUsers = users.value.length
    const activeUsers = users.value.filter(user => user.is_active).length
    const adminUsers = users.value.filter(user => user.role === 'admin').length
    const apiKeys = users.value.filter(user => user.api_key).length

    return {
        totalUsers,
        activeUsers,
        adminUsers,
        apiKeys
    }
})

// Methods
const fetchUsers = async () => {
    try {
        isLoading.value = true

        const params = {
            limit: pagination.value.limit,
            offset: pagination.value.offset
        }

        if (filters.value.search) params.search = filters.value.search
        if (filters.value.role) params.role = filters.value.role
        if (filters.value.status) params.is_active = filters.value.status === 'active'

        const response = await api.get('/admin/users', {params})

        users.value = response.data.users || response.data || []
        totalUsers.value = response.data.total || users.value.length

    } catch (error) {
        console.error('Failed to fetch users:', error)
        toast.error('Failed to load users')
    } finally {
        isLoading.value = false
    }
}

const openCreateUserModal = () => {
    editingUser.value = null
    userForm.value = {
        username: '',
        email: '',
        password: '',
        role: 'user',
        requests_limit: 10000,
        is_active: true,
        generate_api_key: false
    }
    showUserModal.value = true
}

const editUser = (user) => {
    editingUser.value = user
    userForm.value = {
        username: user.username,
        email: user.email,
        password: '',
        role: user.role,
        requests_limit: user.requests_limit,
        is_active: user.is_active,
        generate_api_key: false
    }
    showUserModal.value = true
}

const closeUserModal = () => {
    showUserModal.value = false
    editingUser.value = null
}

const saveUser = async () => {
    try {
        isSaving.value = true

        if (editingUser.value) {
            // Update user
            const response = await api.put(`/admin/users/${editingUser.value.id}`, userForm.value)

            // Update user in list
            const index = users.value.findIndex(u => u.id === editingUser.value.id)
            if (index !== -1) {
                users.value[index] = {...users.value[index], ...response.data}
            }

            toast.success('User updated successfully')
        } else {
            // Create user
            const response = await api.post('/admin/users', userForm.value)
            users.value.unshift(response.data)
            toast.success('User created successfully')
        }

        closeUserModal()
    } catch (error) {
        console.error('Failed to save user:', error)
        toast.error('Failed to save user')
    } finally {
        isSaving.value = false
    }
}

const toggleUserStatus = async (user) => {
    try {
        const newStatus = !user.is_active
        await api.put(`/admin/users/${user.id}`, {is_active: newStatus})

        user.is_active = newStatus
        toast.success(`User ${newStatus ? 'activated' : 'deactivated'} successfully`)
    } catch (error) {
        console.error('Failed to toggle user status:', error)
        toast.error('Failed to update user status')
    }
}

const deleteUser = async (user) => {
    if (!confirm(`Are you sure you want to delete user "${user.username}"? This action cannot be undone.`)) {
        return
    }

    try {
        await api.delete(`/admin/users/${user.id}`)

        const index = users.value.findIndex(u => u.id === user.id)
        if (index !== -1) {
            users.value.splice(index, 1)
        }

        toast.success('User deleted successfully')
    } catch (error) {
        console.error('Failed to delete user:', error)
        toast.error('Failed to delete user')
    }
}

const previousPage = () => {
    if (pagination.value.offset > 0) {
        pagination.value.offset = Math.max(0, pagination.value.offset - pagination.value.limit)
        fetchUsers()
    }
}

const nextPage = () => {
    if (pagination.value.offset + pagination.value.limit < totalUsers.value) {
        pagination.value.offset += pagination.value.limit
        fetchUsers()
    }
}

// Debounced search
const debounceSearch = debounce(() => {
    pagination.value.offset = 0
    fetchUsers()
}, 500)

// Utility functions
const formatDate = (dateString) => {
    return format(new Date(dateString), 'MMM dd, yyyy')
}

const getUserInitials = (user) => {
    return user.username
        .split(' ')
        .map(name => name.charAt(0))
        .join('')
        .toUpperCase()
        .slice(0, 2)
}

const getRoleClass = (role) => {
    return role === 'admin'
        ? 'bg-purple-100 text-purple-800'
        : 'bg-blue-100 text-blue-800'
}

const getStatusClass = (isActive) => {
    return isActive
        ? 'bg-green-100 text-green-800'
        : 'bg-red-100 text-red-800'
}

const getUsagePercentage = (user) => {
    if (!user.requests_limit || user.requests_limit === 0) return 0
    return Math.min(100, (user.requests_used / user.requests_limit) * 100)
}

// Lifecycle
onMounted(() => {
    fetchUsers()
})
</script>
