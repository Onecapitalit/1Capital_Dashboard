import os
import sys
import django
import pandas as pd
from pathlib import Path
from decimal import Decimal
import re

# sys.path.insert(0, 'H:\\SalesDashboardProject\\SalesDashboard')
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_ROOT = PROJECT_ROOT / 'data_files'

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import Employee, Client, SalesRecord, UserProfile, EmployeeWireCode, SalesRecordAAABrokerage, SalesRecordMF
from core.data_pipeline import DataPipeline
from django.contrib.auth.models import User
from django.db import transaction

print("="*100)
print("COMPLETE DATABASE RESET AND FULL DATA LOAD")
print("="*100)

# Initialize pipeline
dp = DataPipeline()

# Step 1: Clear all data
print("\n[1/7] Clearing existing data...")
print("-"*100)
SalesRecordMF.objects.all().delete()
SalesRecordAAABrokerage.objects.all().delete()
SalesRecord.objects.all().delete()
Client.objects.all().delete()
UserProfile.objects.filter(employee__isnull=False).update(employee=None)
EmployeeWireCode.objects.all().delete()
Employee.objects.all().delete()
print("[OK] Cleared all data")

# Step 2: Load employees
print("\n[2/7] Loading Employee Dimension...")
print("-"*100)
employee_count = dp._load_employee_dimension()
print(f"[OK] Employees Loaded: {employee_count}")

# Step 2b: Build hierarchy
print(f"\n[2b/7] Building Employee Hierarchy...")
print("-"*100)
hierarchy_count = dp._build_employee_hierarchy()
print(f"[OK] Manager Links: {hierarchy_count}")

# Step 3: Load all clients
print(f"\n[3/7] Loading Client Dimension...")
print("-"*100)
client_count = dp._load_client_dimension()
print(f"[OK] Clients Loaded: {client_count}")

# Step 4: Load brokerage facts
print(f"\n[4/7] Loading Brokerage Facts...")
print("-"*100)
brokerage_count = dp._load_brokerage_facts()
print(f"[OK] Brokerage Records Loaded: {brokerage_count}")

# Step 5: Load MF facts
print("\n[5/7] Loading MF Facts...")
print("-"*100)
mf_count = dp._load_mf_facts()
print(f"[OK] MF Records Loaded: {mf_count}")

# Step 5b: Load specialized AAA Brokerage facts
print("\n[5b/7] Loading Specialized AAA Brokerage Facts...")
print("-"*100)
aaa_count = dp._load_aaa_brokerage_facts()
print(f"[OK] AAA Brokerage Records Loaded: {aaa_count}")

# Step 5c: Load specialized MF facts
print("\n[5c/7] Loading Specialized MF Facts...")
print("-"*100)
special_mf_count = dp._load_specialized_mf_facts()
print(f"[OK] Specialized MF Records Loaded: {special_mf_count}")

# Step 5d: Load specialized client dimensions (WealthMagic & PMS/AIF)
print("\n[5d/7] Loading Specialized Client Dimensions...")
print("-"*100)
wm_count = dp._load_wealthmagic_clients()
print(f"[OK] WealthMagic Clients Loaded: {wm_count}")
pms_client_count = dp._load_pms_aif_clients()
print(f"[OK] PMS/AIF Clients Loaded: {pms_client_count}")

# Step 5e: Load PMS/AIF sales records
print("\n[5e/7] Loading PMS/AIF Sales Records...")
print("-"*100)
pms_aif_sales_count = dp._load_pms_aif_sales_records()
print(f"[OK] PMS/AIF Sales Records Loaded: {pms_aif_sales_count}")

# Step 6: Create/Update all users
print(f"\n[6/7] Creating User Accounts...")
print("-"*100)

password = "Demo@123456"
user_count = 0

for emp in Employee.objects.all().order_by('rm_name'):
    username = emp.rm_name.lower().replace(" ", "_")
    
    user, created = User.objects.get_or_create(username=username, defaults={
        'email': emp.email or f'{username}@onecapital.com',
        'first_name': emp.rm_name.split()[0] if emp.rm_name else '',
        'last_name': ' '.join(emp.rm_name.split()[1:]) if len(emp.rm_name.split()) > 1 else '',
    })
    
    user.set_password(password)
    user.save()
    
    # Create or get profile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.employee = emp
    profile.wire_code = emp.wire_code
    
    # Assign role
    if emp.manager is None:
        profile.role = 'L'
    elif emp.subordinates.exists():
        profile.role = 'M'
    else:
        profile.role = 'R'
    
    profile.save()
    user_count += 1
    print(f"  {emp.rm_name:30} ({username:25})")

# Link UserProfiles
dp._link_userprofile_to_employee()

print(f"[OK] Users Created/Updated: {user_count}")

# Step 7: Summary statistics
print(f"\n[7/7] Final Statistics...")
print("-"*100)

total_brokerage = SalesRecord.objects.filter(data_source='BROKERAGE').aggregate(
    total=django.db.models.Sum('total_brokerage')
)['total'] or 0
total_mf = SalesRecord.objects.filter(data_source='MF').aggregate(
    total=django.db.models.Sum('mf_brokerage')
)['total'] or 0

print(f"\n[OK] Employees: {Employee.objects.count()}")
print(f"[OK] Clients: {Client.objects.count()}")
print(f"[OK] Sales Records: {SalesRecord.objects.count()}")
print(f"  - Brokerage: {brokerage_count} records (Rs.{total_brokerage:,.2f})")
print(f"  - MF: {mf_count} records (Rs.{total_mf:,.2f})")
print(f"[OK] Users: {user_count}")

print("\n" + "="*100)
print("ALL DATA LOADED SUCCESSFULLY!")
print("="*100)
