# Migration: Add self-join manager hierarchy and UserProfile-Employee linking

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_enhanced_data_models'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Add manager self-referential FK to Employee
        migrations.AddField(
            model_name='employee',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                help_text='Manager this employee reports to (self-join hierarchy)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subordinates',
                to='core.employee'
            ),
        ),
        
        # Add is_active to Employee if not present
        migrations.AddField(
            model_name='employee',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True),
        ),
        
        # Create UserProfile model
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('L', 'Leader'), ('M', 'Manager'), ('R', 'RM / MA')], default='R', max_length=1)),
                ('wire_code', models.CharField(blank=True, db_index=True, help_text='Wire/Employee code for matching with data', max_length=50, null=True)),
                ('is_active', models.BooleanField(default=True, help_text='User can login if True')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.OneToOneField(blank=True, help_text='Link to Employee dimension (RM master data)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user_profile', to='core.employee')),
                ('reporting_to', models.ForeignKey(blank=True, help_text='Manager this user reports to (creates hierarchy)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='direct_reports', to='core.userprofile')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to='auth.user')),
            ],
            options={
                'db_table': 'user_profile',
            },
        ),
        
        # Add indexes for UserProfile
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['wire_code'], name='user_profile_wire_code_idx'),
        ),
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['role'], name='user_profile_role_idx'),
        ),
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['reporting_to'], name='user_profile_reporting_to_idx'),
        ),
        
        # Add index for Employee.manager
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['manager'], name='employee_dimension_manager_idx'),
        ),
        
        # Add index for Employee.is_active
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['is_active'], name='employee_dimension_is_active_idx'),
        ),
    ]
