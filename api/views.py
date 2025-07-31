# api/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from .models import Customer, Loan
from .serializers import CustomerRegistrationSerializer, LoanEligibilityCheckSerializer, LoanDetailSerializer, CustomerLoanViewSerializer
from decimal import Decimal

class RegisterCustomerView(generics.CreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        response_data = {
            "customer_id": serializer.instance.customer_id,
            "name": f"{serializer.instance.first_name} {serializer.instance.last_name}",
            "age": serializer.instance.age,
            "monthly_income": serializer.instance.monthly_salary,
            "approved_limit": serializer.instance.approved_limit,
            "phone_number": serializer.instance.phone_number,
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

class CheckEligibilityView(generics.GenericAPIView):
    serializer_class = LoanEligibilityCheckSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        loan_amount = serializer.validated_data['loan_amount']
        interest_rate = serializer.validated_data['interest_rate']
        tenure = serializer.validated_data['tenure']

        eligibility_result = serializer.get_eligibility_result(
            requested_loan_amount=loan_amount,
            requested_interest_rate=interest_rate,
            requested_tenure=tenure
        )
        return Response(eligibility_result, status=status.HTTP_200_OK)

class CreateLoanView(generics.CreateAPIView):
    queryset = Loan.objects.all()
    serializer_class = LoanEligibilityCheckSerializer # Reusing the eligibility serializer for request validation

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # The serializer's create method handles eligibility check and loan creation
        # It returns the structured response data directly
        response_data = serializer.create(serializer.validated_data) # Call the create method defined in serializer

        if response_data['loan_approved']:
            status_code = status.HTTP_201_CREATED
        else:
            status_code = status.HTTP_200_OK # Or 400 Bad Request, but 200 OK with approval=False is common for eligibility checks

        return Response(response_data, status=status_code)
    




class ViewLoanDetailView(generics.RetrieveAPIView):
    queryset = Loan.objects.all()
    serializer_class = LoanDetailSerializer
    lookup_field = 'loan_id' # This tells DRF to use loan_id from the URL as the lookup field


class ViewCustomerLoansView(generics.ListAPIView):
    serializer_class = CustomerLoanViewSerializer

    def get_queryset(self):
        customer_id = self.kwargs['customer_id'] # Get customer_id from URL 
        queryset = Loan.objects.filter(customer__customer_id=customer_id, loan_status='active') # Filter by customer_id and active loans
        return queryset

    # Customize response if customer not found or no loans, though DRF's ListAPIView handles empty queryset
    # well. For a custom message for "customer not found", we would override list method.
    # For now, an empty list is fine for no loans.
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():
            # Check if customer exists at all before returning empty.
            # If customer_id is invalid, get_queryset would return empty list.
            # To differentiate:
            try:
                Customer.objects.get(customer_id=self.kwargs['customer_id'])
            except Customer.DoesNotExist:
                return Response({"detail": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
            
            return Response([], status=status.HTTP_200_OK) # Return empty list if customer exists but has no loans

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
