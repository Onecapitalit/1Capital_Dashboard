@echo off
REM Activate virtual environment
pause
call "venv\Scripts\activate.bat"

REM Install pandas and Django (requirements.txt is optional)
pip install pandas
pip install django

REM Run migrations
python SalesDashboard/manage.py migrate

REM Load sales data
python SalesDashboard/manage.py load_sales_data

REM Start the Django server
echo Starting Django server at http://127.0.0.1:8000/
python SalesDashboard/manage.py runserver

