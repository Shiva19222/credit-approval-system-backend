# api/serializers.py
from rest_framework import serializers
from .models import Customer, Loan
from decimal import Decimal
from datetime import datetime, date
from django.db.models import Sum
from django.utils import timezone
from django.db import transaction
from dateutil.relativedelta import relativedelta


class CustomerRegistrationSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(required=True)
    monthly_income = serializers.DecimalField(max_digits=10, decimal_places=2, source='monthly_salary', required=True)

    class Meta:
        model = Customer
        fields = ['first_name', 'last_name', 'age', 'monthly_income', 'phone_number']
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'phone_number': {'required': True},
        }

    def create(self, validated_data):
        monthly_salary = validated_data['monthly_salary']
        calculated_approved_limit = Decimal(36) * monthly_salary
        approved_limit = Decimal(round(calculated_approved_limit / 100000) * 100000) # Rounded to nearest lakh

        customer = Customer.objects.create(
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            age=validated_data['age'],
            phone_number=validated_data['phone_number'],
            monthly_salary=monthly_salary,
            approved_limit=approved_limit,
            current_debt=Decimal('0.00') # New customers start with no debt
        )
        return customer


class LoanEligibilityCheckSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField(required=True)
    loan_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=True)
    tenure = serializers.IntegerField(required=True)

    def validate(self, data):
        try:
            self.customer = Customer.objects.get(customer_id=data['customer_id'])
        except Customer.DoesNotExist:
            raise serializers.ValidationError({"customer_id": "Customer not found."})
        return data

    def calculate_credit_score(self):
        customer = self.customer
        credit_score = 100 # Start with max score

        all_loans = Loan.objects.filter(customer=customer)
        active_loans = all_loans.filter(loan_status='active')

        # Criteria 1: Past Loans paid on time
        total_emis_paid = all_loans.aggregate(Sum('emis_paid_on_time'))['emis_paid_on_time__sum']
        total_tenure = all_loans.aggregate(Sum('tenure'))['tenure__sum']

        total_emis_paid = total_emis_paid if total_emis_paid is not None else 0
        total_tenure = total_tenure if total_tenure is not None else 0

        if total_tenure > 0:
            on_time_percentage = (total_emis_paid / total_tenure) * 100
            if on_time_percentage < 50:
                credit_score -= 10
            elif on_time_percentage < 70:
                credit_score -= 5

        # Criteria 2: No. of loans taken in past
        num_past_loans = all_loans.count()
        if num_past_loans > 5:
            credit_score -= 10
        elif num_past_loans > 2:
            credit_score -= 5

        # Criteria 3: Loan activity in current year
        current_year = timezone.now().year
        loans_current_year = all_loans.filter(start_date__year=current_year).count()
        if loans_current_year > 2:
            credit_score -= 8 # High recent activity might be a slight risk

        # Criteria 4: Loan approved volume
        total_loan_amount_approved = all_loans.aggregate(Sum('loan_amount'))['loan_amount__sum']
        total_loan_amount_approved = total_loan_amount_approved if total_loan_amount_approved is not None else Decimal('0.00')

        if customer.approved_limit and customer.approved_limit > 0:
            if total_loan_amount_approved > customer.approved_limit * Decimal('1.5'):
                credit_score -= 15

        # Criteria 5: If sum of current loans of customer > approved limit of customer, credit score = 0
        total_current_loan_amount = active_loans.aggregate(Sum('loan_amount'))['loan_amount__sum']
        total_current_loan_amount = total_current_loan_amount if total_current_loan_amount is not None else Decimal('0.00')

        if customer.approved_limit and customer.approved_limit > 0 and total_current_loan_amount > customer.approved_limit:
            credit_score = 0

        # Ensure score doesn't go below 0
        return max(0, credit_score)

    def calculate_emi(self, loan_amount, interest_rate, tenure):
        # Compound interest scheme
        # EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
        # where P = Principal Loan Amount, r = Monthly Interest Rate, n = Tenure in Months
        
        if interest_rate == 0:
            return loan_amount / tenure # Simple calculation if interest rate is 0 to avoid division by zero

        # Convert annual interest rate to monthly interest rate (decimal)
        monthly_interest_rate = (interest_rate / 12) / Decimal('100')
        
        # Use Decimal for calculations to maintain precision
        pow_factor = (Decimal('1') + monthly_interest_rate)**tenure
        
        numerator = loan_amount * monthly_interest_rate * pow_factor
        denominator = pow_factor - Decimal('1')
        
        if denominator == 0:
            # This can happen if monthly_interest_rate is very small and tenure is not too large,
            # causing pow_factor to be 1. Treat as simple interest.
            return loan_amount / tenure

        emi = numerator / denominator
        return emi.quantize(Decimal('0.01')) # Round to 2 decimal places

    def get_eligibility_result(self, requested_loan_amount, requested_interest_rate, requested_tenure):
        customer = self.customer
        credit_score = self.calculate_credit_score()

        approval = False
        corrected_interest_rate = requested_interest_rate
        monthly_installment = Decimal('0.00')

        # Rule: If sum of all current EMIs > 50% of monthly salary, don't approve any loans
        total_current_emis = Loan.objects.filter(customer=customer, loan_status='active').aggregate(Sum('monthly_repayment'))['monthly_repayment__sum']
        total_current_emis = total_current_emis if total_current_emis is not None else Decimal('0.00')
        
        if (customer.monthly_salary and customer.monthly_salary > 0) and total_current_emis > (customer.monthly_salary / Decimal('2')):
            return {
                "customer_id": customer.customer_id,
                "approval": False,
                "interest_rate": requested_interest_rate,
                "corrected_interest_rate": requested_interest_rate,
                "tenure": requested_tenure,
                "monthly_installment": monthly_installment,
            }

        # Approval logic based on credit score
        if credit_score > 50:
            approval = True
        elif 30 < credit_score <= 50:
            if requested_interest_rate < Decimal('12.00'): # If requested is lower than allowed minimum
                corrected_interest_rate = Decimal('12.00')
            approval = True
        elif 10 < credit_score <= 30:
            if requested_interest_rate < Decimal('16.00'): # If requested is lower than allowed minimum
                corrected_interest_rate = Decimal('16.00')
            approval = True
        else: # credit_score <= 10
            approval = False
        
        # This 'if approval:' block MUST be at the same indentation level as the if/elif/else above.
        if approval:
            # Check if loan amount exceeds approved_limit for this new loan
            if customer.approved_limit is None or customer.approved_limit == Decimal('0.00'):
                if requested_loan_amount > Decimal('0.00'):
                    approval = False # Deny if no approved limit set and loan amount is non-zero
            elif requested_loan_amount > customer.approved_limit:
                approval = False
            else:
                monthly_installment = self.calculate_emi(
                    requested_loan_amount,
                    corrected_interest_rate,
                    requested_tenure
                )
        
        return {
            "customer_id": customer.customer_id,
            "approval": approval,
            "interest_rate": requested_interest_rate,
            "corrected_interest_rate": corrected_interest_rate,
            "tenure": requested_tenure,
            "monthly_installment": monthly_installment,
        }

    # Add a create method for loan processing (used by /create-loan endpoint)
    def create(self, validated_data):
        customer = self.customer # customer is already fetched in validate method
        loan_amount = validated_data['loan_amount']
        interest_rate = validated_data['interest_rate']
        tenure = validated_data['tenure']

        # Determine eligibility using the logic already defined
        eligibility_result = self.get_eligibility_result(loan_amount, interest_rate, tenure)

        if eligibility_result['approval']:
            start_date = timezone.now().date()
            end_date = start_date + relativedelta(months=tenure)

            monthly_installment = self.calculate_emi(
                loan_amount,
                eligibility_result['corrected_interest_rate'],
                tenure
            )

            with transaction.atomic():
                loan = Loan.objects.create(
                    customer=customer,
                    loan_amount=loan_amount,
                    tenure=tenure,
                    interest_rate=eligibility_result['corrected_interest_rate'], # Store corrected rate
                    monthly_repayment=monthly_installment,
                    emis_paid_on_time=0, # New loan starts with 0 EMIs paid on time
                    start_date=start_date,
                    end_date=end_date,
                    loan_status='active'
                )
                # Update customer's current_debt
                customer.current_debt += loan_amount
                customer.save()
            
            return {
                "loan_id": loan.loan_id,
                "customer_id": customer.customer_id,
                "loan_approved": True,
                "message": "Loan approved successfully",
                "monthly_installment": monthly_installment,
            }
        else:
            return {
                "loan_id": None,
                "customer_id": customer.customer_id,
                "loan_approved": False,
                "message": "Loan not approved based on eligibility criteria",
                "monthly_installment": Decimal('0.00'),
            }




# api/serializers.py (add this at the bottom of the file)
# Make sure to add it outside any other class definitions

# api/serializers.py

# ... (other serializers and imports) ...

class CustomerDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['customer_id', 'first_name', 'last_name', 'phone_number', 'age']

class LoanDetailSerializer(serializers.ModelSerializer):
    customer = CustomerDetailSerializer(read_only=True)

    class Meta:
        model = Loan
        # Change 'monthly_installment' to 'monthly_repayment' as per your model
        fields = ['loan_id', 'customer', 'loan_amount', 'interest_rate', 'monthly_repayment', 'tenure'] # <-- CORRECTED


# api/serializers.py (add this at the bottom of the file)
# Make sure to add it outside any other class definitions

class CustomerLoanViewSerializer(serializers.ModelSerializer):
    repayments_left = serializers.SerializerMethodField() # Custom field for EMIs left

    class Meta:
        model = Loan
        # Fields expected in the response list for a customer's loans [cite: 6, 87]
        fields = ['loan_id', 'loan_amount', 'interest_rate', 'monthly_repayment', 'repayments_left']

    def get_repayments_left(self, obj):
        # This calculates remaining EMIs for active loans.
        # Assuming current_debt and total_monthly_repayment reflect the remaining.
        # For simplicity, if current_debt is based on loan_amount, then:
        # remaining EMIs = current_debt / monthly_repayment.
        # Or, it could mean total_tenure - emis_paid_on_time for past EMIs.
        # Let's interpret 'repayments_left' as `tenure - emis_paid_on_time` for active loans
        # if monthly_repayment > 0 else 0
        
        # A more robust calculation would track payments made.
        # For now, based on provided data schema:
        return max(0, obj.tenure - obj.emis_paid_on_time)