# api/tasks.py
import pandas as pd
from celery import shared_task
from django.db import transaction
from api.models import Customer, Loan
from decimal import Decimal
from datetime import datetime
import numpy as np


@shared_task
def ingest_customer_data_task(file_path):
    try:
        df = pd.read_csv(file_path, encoding='latin1')
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.lower()

        # --- UPDATED EXPECTED COLUMNS FOR CUSTOMER DATA ---
        # 'age' is not in the original customer_data.xlsx, but it's expected by the model.
        # The error log shows 'age' is present, so let's include it here.
        expected_cols_customer = ['customer_id', 'first_name', 'last_name', 'phone_number',
                                  'monthly_salary', 'approved_limit', 'age']

        # Check if all expected columns (excluding current_debt, as it's generated/defaulted) exist
        if not all(col in df.columns for col in expected_cols_customer):
            missing_cols = [col for col in expected_cols_customer if col not in df.columns]
            raise ValueError(f"Missing crucial columns in customer data CSV: {missing_cols}. Actual columns after cleaning: {list(df.columns)}")

        # Convert relevant columns to numeric, coercing errors to NaN
        df_clean = df.copy()
        for col in ['customer_id', 'monthly_salary', 'approved_limit', 'age']:
            if col in df_clean.columns:
                df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
                df_clean[col] = df_clean[col].fillna(0) # Fill NaN with 0

        customers_to_create = []

        for index, row in df_clean.iterrows():
            if not isinstance(row['customer_id'], (int, float)) or pd.isna(row['customer_id']) or int(row['customer_id']) == 0:
                print(f"Skipping customer row due to invalid customer_id: {row.to_dict()}")
                continue

            try:
                monthly_salary = Decimal(str(row['monthly_salary']))
                calculated_approved_limit = Decimal(36) * monthly_salary
                approved_limit = Decimal(round(calculated_approved_limit / 100000) * 100000)
                
                # current_debt is NOT in the source CSV, so we initialize it to 0.00
                current_debt_val = Decimal('0.00') 

                customers_to_create.append(
                    Customer(
                        customer_id=int(row['customer_id']),
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        phone_number=str(row['phone_number']),
                        monthly_salary=monthly_salary,
                        approved_limit=approved_limit,
                        current_debt=current_debt_val,
                        age=int(row['age'])
                    )
                )
            except Exception as e:
                print(f"Error processing customer row {row.get('customer_id', 'N/A')}: {e}. Row data: {row.to_dict()}")

        with transaction.atomic():
            Customer.objects.bulk_create(customers_to_create, ignore_conflicts=True)

        print(f"Successfully ingested {len(customers_to_create)} customer records.")
    except Exception as e:
        print(f"Error ingesting customer data: {e}")

@shared_task
def ingest_loan_data_task(file_path):
    try:
        df = pd.read_csv(file_path, encoding='latin1')
        df.columns = df.columns.str.strip().str.replace(' ', '_').str.lower()

        # --- UPDATED EXPECTED COLUMNS FOR LOAN DATA ---
        expected_cols_loan = ['customer_id', 'loan_id', 'loan_amount', 'tenure',
                                  'interest_rate', 'monthly_payment', 'emis_paid_on_time',
                                  'date_of_approval', 'end_date']

        if not all(col in df.columns for col in expected_cols_loan):
            missing_cols = [col for col in expected_cols_loan if col not in df.columns]
            raise ValueError(f"Missing crucial columns in loan data CSV: {missing_cols}. Actual columns after cleaning: {list(df.columns)}")


        # Convert relevant columns to numeric, coercing errors to NaN
        df_clean = df.copy()
        for col in ['customer_id', 'loan_id', 'loan_amount', 'tenure', 'interest_rate',
                    'monthly_payment', 'emis_paid_on_time']:
            if col in df_clean.columns:
                df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
                df_clean[col] = df_clean[col].fillna(0) # Fill NaN values with 0

        loans_to_create = []

        for index, row in df_clean.iterrows():
            if not isinstance(row['customer_id'], (int, float)) or pd.isna(row['customer_id']) or int(row['customer_id']) == 0:
                print(f"Skipping loan row due to invalid customer_id: {row.to_dict()}")
                continue
            if not isinstance(row['loan_id'], (int, float)) or pd.isna(row['loan_id']) or int(row['loan_id']) == 0:
                print(f"Skipping loan row due to invalid loan_id: {row.to_dict()}")
                continue

            try:
                customer_id = int(row['customer_id'])
                customer = Customer.objects.get(customer_id=customer_id)

                # --- MAPPING CSV COLUMN NAMES TO MODEL FIELD NAMES ---
                start_date_str = str(row['date_of_approval'])
                end_date_str = str(row['end_date'])
                monthly_repayment_val = Decimal(str(row['monthly_payment']))


                if pd.isna(row['date_of_approval']) or not start_date_str:
                    print(f"Warning: Skipping loan {row.get('loan_id', 'N/A')} due to missing date_of_approval.")
                    continue
                if pd.isna(row['end_date']) or not end_date_str:
                    print(f"Warning: Skipping loan {row.get('loan_id', 'N/A')} due to missing end_date.")
                    continue

                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        start_date = datetime.strptime(start_date_str, '%m/%d/%Y').date()
                    except ValueError:
                        print(f"Could not parse start_date '{start_date_str}' for loan {row.get('loan_id', 'N/A')}. Skipping loan.")
                        continue

                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        end_date = datetime.strptime(end_date_str, '%m/%d/%Y').date()
                    except ValueError:
                        print(f"Could not parse end_date '{end_date_str}' for loan {row.get('loan_id', 'N/A')}. Skipping loan.")
                        continue

                loans_to_create.append(
                    Loan(
                        customer=customer,
                        loan_amount=Decimal(str(row['loan_amount'])),
                        tenure=int(row['tenure']),
                        interest_rate=Decimal(str(row['interest_rate'])),
                        monthly_repayment=monthly_repayment_val,
                        emis_paid_on_time=int(row['emis_paid_on_time']),
                        start_date=start_date,
                        end_date=end_date,
                        loan_status='active'
                    )
                )
            except Customer.DoesNotExist:
                print(f"Customer with ID {row.get('customer_id', 'N/A')} not found for loan ID {row.get('loan_id', 'N/A')}. Skipping loan.")
            except Exception as e:
                loan_id_info = row.get('loan_id', 'N/A')
                customer_id_info = row.get('customer_id', 'N/A')
                print(f"Error processing loan {loan_id_info} for customer {customer_id_info}: {e}. Row data: {row.to_dict()}")

        with transaction.atomic():
            Loan.objects.bulk_create(loans_to_create, ignore_conflicts=True)
        print(f"Successfully ingested {len(loans_to_create)} loan records.")
    except Exception as e:
        print(f"Error ingesting loan data: {e}")