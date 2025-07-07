import {createRouter, createWebHistory} from 'vue-router'
import {useAuthStore} from '../stores/auth'

// Lazy load components
const Dashboard = () => import('../views/Dashboard.vue')
const Login = () => import('../views/Login.vue')
const Modems = () => import('../views/Modems.vue')
const ModemDetail = () => import('../views/ModemDetail.vue')
const Statistics = () => import('../views/Statistics.vue')
const Logs = () => import('../views/Logs.vue')
const Settings = () => import('../views/Settings.vue')
const Users = () => import('../views/Users.vue')
const NotFound = () => import('../views/NotFound.vue')

const routes = [
    {
        path: '/',
        redirect: '/dashboard'
    },
    {
        path: '/login',
        name: 'Login',
        component: Login,
        meta: {
            requiresAuth: false,
            title: 'Login'
        }
    },
    {
        path: '/dashboard',
        name: 'Dashboard',
        component: Dashboard,
        meta: {
            requiresAuth: true,
            title: 'Dashboard'
        }
    },
    {
        path: '/dedicated-proxies',
        name: 'DedicatedProxies',
        component: () => import('../components/DedicatedProxyManager.vue'),
        meta: {requiresAuth: true, requiresAdmin: true}
    },
    {
        path: '/modems',
        name: 'Modems',
        component: Modems,
        meta: {
            requiresAuth: true,
            title: 'Modems'
        }
    },
    {
        path: '/modems/:id',
        name: 'ModemDetail',
        component: ModemDetail,
        meta: {
            requiresAuth: true,
            title: 'Modem Details'
        }
    },
    {
        path: '/statistics',
        name: 'Statistics',
        component: Statistics,
        meta: {
            requiresAuth: true,
            title: 'Statistics'
        }
    },
    {
        path: '/logs',
        name: 'Logs',
        component: Logs,
        meta: {
            requiresAuth: true,
            title: 'Logs'
        }
    },
    {
        path: '/settings',
        name: 'Settings',
        component: Settings,
        meta: {
            requiresAuth: true,
            title: 'Settings',
            requiresAdmin: true
        }
    },
    {
        path: '/users',
        name: 'Users',
        component: Users,
        meta: {
            requiresAuth: true,
            title: 'Users',
            requiresAdmin: true
        }
    },
    {
        path: '/404',
        name: 'NotFound',
        component: NotFound,
        meta: {
            title: 'Page Not Found'
        }
    },
    {
        path: '/:pathMatch(.*)*',
        redirect: '/404'
    }
]

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes,
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) {
            return savedPosition
        } else {
            return {top: 0}
        }
    }
})

// Navigation guards
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()

    // Set page title
    document.title = to.meta.title
        ? `${to.meta.title} - Mobile Proxy Admin`
        : 'Mobile Proxy Admin'

    // Check if route requires authentication
    if (to.meta.requiresAuth) {
        if (!authStore.isAuthenticated) {
            // Try to restore auth from localStorage
            await authStore.restoreAuth()

            if (!authStore.isAuthenticated) {
                next('/login')
                return
            }
        }

        // Check admin permissions
        if (to.meta.requiresAdmin && !authStore.isAdmin) {
            next('/dashboard')
            return
        }
    }

    // Redirect authenticated users from login page
    if (to.name === 'Login' && authStore.isAuthenticated) {
        next('/dashboard')
        return
    }

    next()
})

export default router
