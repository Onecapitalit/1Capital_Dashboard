import pandas as pd
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from core.models import SalesRecord, UserProfile
from django.db import transaction

class Command(BaseCommand):
    help = 'Loads sales data from a CSV file placed in the data_files folder.'

    def handle(self, *args, **options):
        # 1. Define the file path using a more direct calculation.
        project_root = settings.BASE_DIR.parent 
        file_path = project_root / 'data_files' / 'sales_data.csv'

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f"CSV file not found at: {file_path.resolve()}. Please verify the data_files folder and file location."))
            return

        self.stdout.write(self.style.SUCCESS('--- Starting Data Load ---'))

        # 2. Clear existing sales data (always wipe before loading new)
        SalesRecord.objects.all().delete()
        self.stdout.write(self.style.WARNING('Cleared existing SalesRecord data.'))

        # 3. Use Pandas to read the CSV file
        try:
            df = pd.read_csv(str(file_path)) 
            df.columns = df.columns.str.strip() 
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading CSV: {e}"))
            return

        # 4. Iterate through data and save to database
        total_records = len(df)
        records_created = 0


        debug_dates = []
        with transaction.atomic():
            all_parsed_dates = []
            for index, row in df.iterrows():

                rm_username_raw = row.get('RM_Username')
                if rm_username_raw is None:
                    self.stdout.write(self.style.WARNING(f"Skipping record at index {index}: Missing RM_Username column."))
                    continue
                rm_username = str(rm_username_raw).strip()
                try:
                    rm_user = User.objects.get(username=rm_username)
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Skipping record for missing RM: {rm_username}. Ensure user exists and username matches CSV."))
                    continue

                # Parse DATE column (force dd-mm-yyyy)
                import datetime
                date_str = str(row.get('DATE', '')).strip()
                # Robust date parsing: strip whitespace and try multiple formats
                import re
                cleaned_date = re.sub(r'[^0-9\-/]', '', date_str.strip())
                parsed_date = None
                for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d'):
                    try:
                        parsed_date = datetime.datetime.strptime(cleaned_date, fmt)
                        break
                    except Exception:
                        continue
                if not parsed_date:
                    self.stdout.write(self.style.ERROR(f"Row {index}: Could not parse DATE raw='{repr(date_str)}' cleaned='{cleaned_date}' (Client={row.get('Client_Name')}), tried formats: %d-%m-%Y, %d/%m/%Y, %Y-%m-%d, %Y/%m/%d"))
                    parsed_date = datetime.datetime.now()

                if len(debug_dates) < 5:
                    self.stdout.write(self.style.NOTICE(f"Row {index}: DATE='{date_str}' Parsed={parsed_date.date()} Client={row.get('Client_Name')}"))
                debug_dates.append(parsed_date.date())
                all_parsed_dates.append(parsed_date.date())

                SalesRecord.objects.create(
                    client_name=row['Client_Name'],
                    client_id=row['Client_ID'],
                    brokerage_equity=str(row['Brokerage_Equity']), 
                    brokerage_mf=str(row['Brokerage_MF']),
                    relationship_manager=rm_user,
                    created_at=parsed_date
                )
                records_created += 1

        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully loaded {records_created} of {total_records} records.'))
        # Print unique parsed dates for debugging
        unique_dates = sorted(set(all_parsed_dates))
        self.stdout.write(self.style.NOTICE(f"Unique parsed dates loaded: {len(unique_dates)}"))
        if unique_dates:
            self.stdout.write(self.style.NOTICE(f"First 5 dates: {unique_dates[:5]} ... Last 5 dates: {unique_dates[-5:]}"))

        # Print min/max created_at and count for confirmation
        qs = SalesRecord.objects.all()
        if qs.exists():
            min_date = qs.order_by('created_at').first().created_at
            max_date = qs.order_by('-created_at').first().created_at
            self.stdout.write(self.style.SUCCESS(f"Loaded records from {min_date.date()} to {max_date.date()} (total: {qs.count()})"))
        else:
            self.stdout.write(self.style.WARNING('No records found after load!'))
