# Sales Dashboard

A Django-based sales dashboard application that visualizes sales data with interactive charts and filters.

## Features
- Interactive charts showing sales performance
- Date range filtering
- Manager and RM filters
- Data loading from CSV files
- User authentication
- Responsive design

## Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/shwetajoshi8380/sales-dashboard_sample.git
cd sales-dashboard_sample
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

3. Install required packages:
```bash
pip install django pandas
```

4. Apply database migrations:
```bash
cd SalesDashboard
python manage.py migrate
```

5. Load sample sales data:
```bash
python manage.py load_sales_data
```

6. Create a superuser (admin account):
```bash
python manage.py createsuperuser
```

## Running the Application

You can start the application using the provided batch file:
```bash
start_dashboard.bat
```

Or manually run:
```bash
cd SalesDashboard
python manage.py runserver
```

Then open your browser and navigate to: http://127.0.0.1:8000/

## Data Files
Sample sales data is included in the `data_files/sales_data.csv` file. You can replace this with your own data following the same format.