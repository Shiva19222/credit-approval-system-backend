# api/models.py
from django.db import models

from django.db import models

class Customer(models.Model):
    # Change back to AutoField to allow Django to auto-generate IDs for new registrations
    customer_id = models.AutoField(primary_key=True) # CHANGED BACK TO AUTOFIELD
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True)
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2)
    approved_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    age = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.customer_id})"

class Loan(models.Model):
    loan_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loans') # Links to Customer model
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tenure = models.IntegerField()
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2) # e.g., 12.50%
    monthly_repayment = models.DecimalField(max_digits=12, decimal_places=2) # EMI
    emis_paid_on_time = models.IntegerField(default=0) #
    start_date = models.DateField() #
    end_date = models.DateField() #
    loan_status = models.CharField(max_length=20, default='active') # 'active', 'paid', etc.

    def __str__(self):
        return f"Loan {self.loan_id} for Customer {self.customer.customer_id}"