
import os
import sys
import django
from pathlib import Path
from django.db.models import Sum, Q

# Setup Django
BASE_DIR = Path(__file__).resolve().parent / 'SalesDashboard'
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import SalesRecordAAABrokerage

def debug_dhananjay():
    name = "Dhananjay Yadav"
    manager = "Abhijeet Mane"
    
    total = SalesRecordAAABrokerage.objects.filter(rm_name=name).aggregate(Sum('total_brokerage'))['total_brokerage__sum']
    print(f"Total for '{name}' (unfiltered): {total}")
    
    with_manager = SalesRecordAAABrokerage.objects.filter(rm_name=name, rm_manager_name=manager).aggregate(Sum('total_brokerage'))['total_brokerage__sum']
    print(f"Total for '{name}' with manager '{manager}': {with_manager}")
    
    distinct_managers = SalesRecordAAABrokerage.objects.filter(rm_name=name).values_list('rm_manager_name', flat=True).distinct()
    print(f"Managers found for '{name}': {list(distinct_managers)}")

if __name__ == '__main__':
    debug_dhananjay()
