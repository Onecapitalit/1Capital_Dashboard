from django.db import models
from django.contrib.auth.models import User

# --- Role Definitions ---
# L=Leader, M=Manager, R=RM/MA
ROLES = (
    ('L', 'Leader'),
    ('M', 'Manager'),
    ('R', 'RM / MA'),
)

class UserProfile(models.Model):
    """Extends the default User model to add role and reporting hierarchy."""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=1, choices=ROLES, default='R')
    
    # Self-referential ForeignKey: links this user to the person they report to.
    reporting_to = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='direct_reports' # Allows finding all reports easily
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"
        
    # Helper properties for easy role checking in views/templates
    @property
    def is_leader(self):
        return self.role == 'L'
    
    @property
    def is_manager(self):
        return self.role == 'M'

class SalesRecord(models.Model):
    """Holds the individual sales data loaded from the CSV file."""
    
    # Data columns from the file
    client_name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=50) 
    
    # Financial data
    brokerage_equity = models.DecimalField(max_digits=10, decimal_places=2)
    brokerage_mf = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Link to the salesperson (RM/MA). This is the key for filtering data.
    relationship_manager = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='sales_records'
    )
    
    # Timestamp for when the sale happened (set from CSV loader)
    created_at = models.DateTimeField()
    
    def __str__(self):
        return f"{self.client_name} - {self.relationship_manager.username}"
