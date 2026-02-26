# Generated migration for new data models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_remove_salesrecord_brokerage_equity_and_more'),
    ]

    operations = [
        # Create Employee dimension table
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('wire_code', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('rm_name', models.CharField(db_index=True, max_length=255)),
                ('rm_manager_name', models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ('ma_name', models.CharField(blank=True, max_length=255, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('designation', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'employee_dimension',
            },
        ),
        
        # Create Client dimension table
        migrations.CreateModel(
            name='Client',
            fields=[
                ('client_code', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('client_name', models.CharField(db_index=True, max_length=255)),
                ('rm_name', models.CharField(db_index=True, max_length=255)),
                ('rm_manager_name', models.CharField(blank=True, max_length=255, null=True)),
                ('client_type', models.CharField(blank=True, max_length=50, null=True)),
                ('city', models.CharField(blank=True, max_length=100, null=True)),
                ('state', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('wire_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.employee')),
            ],
            options={
                'db_table': 'client_dimension',
            },
        ),
        
        # Update SalesRecord with new fields and foreign keys
        migrations.AddField(
            model_name='salesrecord',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales_records', to='core.employee'),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales_records', to='core.client'),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='mf_brokerage',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='mf_turnover',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='data_source',
            field=models.CharField(choices=[('BROKERAGE', 'Brokerage Fact'), ('MF', 'Mutual Fund Fact')], default='BROKERAGE', max_length=50),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='period',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='file_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='salesrecord',
            name='loaded_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['rm_name'], name='employee_dimension_rm_name_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['rm_manager_name'], name='employee_dimension_rm_manager_name_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['ma_name'], name='employee_dimension_ma_name_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['client_name'], name='client_dimension_client_name_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['rm_name'], name='client_dimension_rm_name_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['wire_code'], name='client_dimension_wire_code_idx'),
        ),
        migrations.AddIndex(
            model_name='salesrecord',
            index=models.Index(fields=['rm_name', 'total_brokerage'], name='sales_record_rm_name_total_brk_idx'),
        ),
        migrations.AddIndex(
            model_name='salesrecord',
            index=models.Index(fields=['client_name', 'rm_name'], name='sales_record_client_rm_idx'),
        ),
        migrations.AddIndex(
            model_name='salesrecord',
            index=models.Index(fields=['period', 'data_source'], name='sales_record_period_source_idx'),
        ),
        
        # Update field db_index for existing fields
        migrations.AlterField(
            model_name='salesrecord',
            name='rm_name',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='salesrecord',
            name='client_name',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='salesrecord',
            name='rm_manager_name',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='salesrecord',
            name='total_brokerage',
            field=models.DecimalField(db_index=True, decimal_places=2, default=0, max_digits=15),
        ),
    ]
