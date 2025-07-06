module.exports = {
  apps: [
    {
      name: 'mobile-proxy-backend',
      cwd: '/var/www/p-service/backend',
      script: '/var/www/p-service/backend/venv/bin/python',
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8000',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        PYTHONPATH: '/var/www/p-service/backend',
        DATABASE_URL: 'postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy',
        REDIS_URL: 'redis://localhost:6379'
      },
      log_file: '/var/www/p-service/logs/backend.log',
      error_file: '/var/www/p-service/logs/backend-error.log',
      out_file: '/var/www/p-service/logs/backend-out.log',
      time: true
    },
    {
      name: 'mobile-proxy-frontend',
      cwd: '/var/www/p-service/frontend',
      script: 'npm',
      args: 'run preview -- --host 0.0.0.0 --port 3000',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '512M',
      env: {
        NODE_ENV: 'production',
        VITE_API_BASE_URL: 'http://192.168.1.50:8000'
      },
      log_file: '/var/www/p-service/logs/frontend.log',
      error_file: '/var/www/p-service/logs/frontend-error.log',
      out_file: '/var/www/p-service/logs/frontend-out.log',
      time: true
    }
  ]
};
