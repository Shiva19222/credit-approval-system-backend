# api/urls.py (add this path)
from django.urls import path
from .views import RegisterCustomerView, CheckEligibilityView, CreateLoanView, ViewLoanDetailView, ViewCustomerLoansView # Import ViewCustomerLoansView

urlpatterns = [
    path('register', RegisterCustomerView.as_view(), name='register_customer'),
    path('check-eligibility', CheckEligibilityView.as_view(), name='check_eligibility'),
    path('create-loan', CreateLoanView.as_view(), name='create_loan'),
    path('view-loan/<int:loan_id>', ViewLoanDetailView.as_view(), name='view_loan_detail'),
    path('view-loans/<int:customer_id>', ViewCustomerLoansView.as_view(), name='view_customer_loans'), # Path for viewing all loans by customer_id 
]