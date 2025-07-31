# api/management/commands/ingest_data.py
import pandas as pd # Still needed for local testing if you ever run this directly
from django.core.management.base import BaseCommand
from api.tasks import ingest_customer_data_task, ingest_loan_data_task # Import tasks from api.tasks

class Command(BaseCommand):
    help = 'Ingests customer and loan data from CSV files using background workers.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting data ingestion...'))

        # Paths to your CSV files within the Docker container's /app directory
        customer_data_path = '/app/customer_data.xlsx - Sheet1.csv'
        loan_data_path = '/app/loan_data.xlsx - Sheet1.csv'

        # Trigger Celery tasks
        ingest_customer_data_task.delay(customer_data_path)
        ingest_loan_data_task.delay(loan_data_path)

        self.stdout.write(self.style.SUCCESS('Data ingestion tasks dispatched to Celery worker.'))
        self.stdout.write(self.style.SUCCESS('Check Celery worker logs for ingestion status.'))