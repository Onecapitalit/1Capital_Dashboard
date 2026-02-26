import os
import sys
import django
import pandas as pd
from pathlib import Path
from decimal import Decimal

# sys.path.insert(0, 'H:\\SalesDashboardProject\\SalesDashboard')
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_ROOT = PROJECT_ROOT / 'data_files'

sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import Employee, Client, SalesRecord, UserProfile
from django.contrib.auth.models import User

print("="*100)
print("COMPLETE DATABASE RESET AND FULL DATA LOAD")
print("="*100)

# Step 1: Clear all data
print("\n[1/7] Clearing existing data...")
print("-"*100)
SalesRecord.objects.all().delete()
Client.objects.all().delete()
UserProfile.objects.filter(employee__isnull=False).update(employee=None)
Employee.objects.all().delete()
print("[OK] Cleared all data")

# Step 2: Load all 23 employees
print("\n[2/7] Loading 23 Employees...")
print("-"*100)
# file_path = Path('H:\\SalesDashboardProject\\data_files\\Employee_dim\\Wirecode_wise_RMdetails.xlsx')
file_path = DATA_ROOT / 'Employee_dim' / 'Wirecode_wise_RMdetails.xlsx'
df = pd.read_excel(file_path, sheet_name='Sheet1')
df.columns = df.columns.str.strip()

employee_map = {}
count = 0

for idx, row in df.iterrows():
    try:
        wire_code = str(row.get('wire code', '')).strip()
        name = str(row.get('NAME', '')).strip()
        manager_id = row.get('MANAGER ID', None)
        
        if not wire_code or not name or str(wire_code).lower() == 'nan':
            continue
        
        # Skip if wire code already processed (duplicates)
        if wire_code in [e['wire_code'] for e in employee_map.values()]:
            continue
        
        if manager_id is None or str(manager_id).lower() == 'null' or pd.isna(manager_id):
            manager_id = None
        else:
            manager_id = int(manager_id)
        
        emp = Employee.objects.create(
            wire_code=wire_code,
            rm_name=name,
            email=str(row.get('PAN', '')).strip() or None,
        )
        
        employee_id = int(row.get('ID', idx + 1))
        employee_map[employee_id] = {'employee': emp, 'wire_code': wire_code, 'name': name, 'manager_id': manager_id}
        count += 1
        print(f"  {count:2}. {name:30} ({wire_code:12})")
        
    except Exception as e:
        continue

# Step 2b: Link managers
print(f"\n[2b/7] Building Employee Hierarchy...")
print("-"*100)

hierarchy_count = 0
for emp_id, data in employee_map.items():
    emp = data['employee']
    manager_id = data['manager_id']
    
    if manager_id and manager_id in employee_map:
        manager_emp = employee_map[manager_id]['employee']
        emp.manager = manager_emp
        emp.save()
        hierarchy_count += 1
        print(f"  {emp.rm_name:30} -> {manager_emp.rm_name:30}")

print(f"[OK] Employees Loaded: {count}")
print(f"[OK] Manager Links: {hierarchy_count}")

# Step 3: Load all clients
print(f"\n[3/7] Loading Clients...")
print("-"*100)

# client_dir = Path('H:\\SalesDashboardProject\\data_files\\Client_dim')
client_dir = DATA_ROOT / 'Client_dim'
client_count = 0

for file_path in sorted(client_dir.glob('*.xlsx')):
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            
            for idx, row in df.iterrows():
                try:
                    client_code = str(row.get('Client ID/PAN', row.get('ClientCode', row.get('Client Code', '')))).strip()
                    client_name = str(row.get('Client Name', row.get('ClientName', ''))).strip()
                    rm_pan = str(row.get('RM Pan', row.get('RM PAN', ''))).strip()
                    
                    if not client_code or not client_name or client_code.lower() == 'nan':
                        continue
                    
                    # Find matching employee by PAN (stored in email field as per load script) or wire_code
                    emp = Employee.objects.filter(email=rm_pan).first()
                    
                    Client.objects.update_or_create(
                        client_code=client_code,
                        defaults={
                            'client_name': client_name,
                            'wire_code': emp,
                            'rm_name': str(row.get('RM', '')).strip() or (emp.rm_name if emp else None),
                        }
                    )
                    client_count += 1
                except:
                    continue
    except Exception as e:
        continue

print(f"[OK] Clients Loaded: {client_count}")

# Step 4: Load brokerage facts
print(f"\n[4/7] Loading Brokerage Facts...")
print("-"*100)

# brokerage_dir = Path('H:\\SalesDashboardProject\\data_files\\brokerage_fact')
brokerage_dir = DATA_ROOT / 'brokerage_fact'
brokerage_count = 0

for file_path in sorted(brokerage_dir.glob('*.xlsx')):
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            
            for idx, row in df.iterrows():
                try:
                    wire_code = str(row.get('WireCode', row.get('wire code', ''))).strip()
                    client_name = str(row.get('ClientName', row.get('Client Name', ''))).strip()
                    total_brokerage = row.get('TotalBrokerage', row.get('Total Brokerage', 0))
                    
                    if not wire_code or wire_code == 'nan':
                        continue
                    
                    # Try to convert to float
                    try:
                        total_brokerage = float(total_brokerage) if total_brokerage else 0
                    except:
                        total_brokerage = 0
                    
                    # Find matching employee
                    emp = Employee.objects.filter(wire_code=wire_code).first()
                    
                    # Get RM name from employee if exists
                    rm_name = emp.rm_name if emp else None
                    
                    SalesRecord.objects.create(
                        employee=emp,
                        wire_code=wire_code,
                        rm_name=rm_name,
                        client_name=client_name,
                        total_brokerage=Decimal(str(total_brokerage)),
                        data_source='BROKERAGE',
                        file_name=file_path.name,
                    )
                    brokerage_count += 1
                except Exception as e:
                    continue
    except Exception as e:
        continue

print(f"[OK] Brokerage Records Loaded: {brokerage_count}")

# Step 5: Load MF facts
print(f"\n[5/7] Loading MF Facts...")
print("-"*100)

# mf_dir = Path('H:\\SalesDashboardProject\\data_files\\MF_fact')
mf_dir = DATA_ROOT / 'MF_fact'
mf_count = 0

for file_path in sorted(mf_dir.glob('*.xlsx')):
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            
            for idx, row in df.iterrows():
                try:
                    wire_code = str(row.get('WireCode', row.get('wire code', row.get('FC', '')))).strip()
                    client_name = str(row.get('ClientName', row.get('Client Name', ''))).strip()
                    mf_brokerage = row.get('MFBrokerage', row.get('MF Brokerage', 0))
                    
                    if not wire_code or wire_code == 'nan':
                        continue
                    
                    try:
                        mf_brokerage = float(mf_brokerage) if mf_brokerage else 0
                    except:
                        mf_brokerage = 0
                    
                    emp = Employee.objects.filter(wire_code=wire_code).first()
                    
                    # Get RM name from employee if exists
                    rm_name = emp.rm_name if emp else None
                    
                    SalesRecord.objects.create(
                        employee=emp,
                        wire_code=wire_code,
                        rm_name=rm_name,
                        client_name=client_name,
                        mf_brokerage=Decimal(str(mf_brokerage)),
                        data_source='MF',
                        file_name=file_path.name,
                    )
                    mf_count += 1
                except Exception as e:
                    continue
    except Exception as e:
        continue

print(f"[OK] MF Records Loaded: {mf_count}")

# Step 6: Create/Update all users
print(f"\n[6/7] Creating User Accounts...")
print("-"*100)

password = "Demo@123456"
user_count = 0

for emp in Employee.objects.filter(is_active=True).order_by('rm_name'):
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
