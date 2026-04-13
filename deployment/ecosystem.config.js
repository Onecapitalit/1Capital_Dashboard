module.exports = {
  apps: [
    {
      name: "sales-backend",
      script: "venv/bin/gunicorn",
      args: "--bind 0.0.0.0:8000 SalesDashboard.wsgi",
      cwd: "/var/www/OneCapitalSalesDashboard/SalesDashboard",
      interpreter: "none",
      env: {
        DJANGO_DEBUG: "False",
        DJANGO_SECRET_KEY: "onecapital",
        PYTHONPATH: "/var/www/OneCapitalSalesDashboard/SalesDashboard",
      },
    },
  ],
};
