
import os
import django
import sys

# Add the project directory to sys.path
sys.path.append(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\SalesDashboard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import UserProfile, SalesRecord
from django.contrib.auth.models import User
from django.db.models import Sum

print("User Roles and RM Linkage:")
for up in UserProfile.objects.all():
    username = up.user.username
    role = up.role
    rm_name = up.employee.rm_name if up.employee else "N/A"
    
    # Calculate what this user sees
    queryset = SalesRecord.objects.all()
    if role == 'L':
        visibility = "All"
    elif role == 'M':
        visibility = "Managed RMs (currently All in view)"
    else:
        user_full_name = up.user.get_full_name() or username.replace('_', ' ').title()
        queryset = queryset.filter(rm_name=user_full_name)
        visibility = f"Only {user_full_name}"
    
    total = queryset.aggregate(Sum('total_brokerage'))['total_brokerage__sum'] or 0
    mf_total = queryset.aggregate(Sum('mf_brokerage'))['mf_brokerage__sum'] or 0
    
    print(f"User: {username:15} | Role: {role} | RM: {rm_name:15} | Visibility: {visibility:30} | Total Seem: {(total+mf_total):,.2f}")
