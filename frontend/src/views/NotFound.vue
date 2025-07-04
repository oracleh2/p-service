<template>
    <div class="min-h-screen bg-gray-50 flex flex-col lg:relative">
        <div class="flex-grow flex flex-col">
            <main class="flex-grow flex flex-col bg-white">
                <div class="flex-grow mx-auto max-w-7xl w-full flex flex-col px-4 sm:px-6 lg:px-8">
                    <div class="flex-shrink-0 my-auto py-16 sm:py-32">
                        <p class="text-sm font-semibold text-primary-600 uppercase tracking-wide">
                            404 error
                        </p>
                        <h1 class="mt-2 text-4xl font-extrabold text-gray-900 tracking-tight sm:text-5xl">
                            Page not found
                        </h1>
                        <p class="mt-2 text-base text-gray-500">
                            Sorry, we couldn't find the page you're looking for.
                        </p>
                        <div class="mt-6">
                            <router-link to="/dashboard" class="btn btn-lg btn-primary">
                                Go back to dashboard
                            </router-link>
                        </div>
                    </div>
                </div>
            </main>
        </div>
        <div class="hidden lg:block lg:absolute lg:inset-y-0 lg:right-0 lg:w-1/2">
            <div
                class="h-full w-full bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center">
                <div class="max-w-lg">
                    <div class="text-center">
                        <WifiIcon class="mx-auto h-24 w-24 text-primary-300"/>
                        <h2 class="mt-4 text-xl font-semibold text-primary-900">
                            Lost in the proxy network?
                        </h2>
                        <p class="mt-2 text-primary-700">
                            Don't worry, our mobile proxies will help you find your way back.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {WifiIcon} from '@heroicons/vue/24/outline'
</script>
