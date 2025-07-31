# credit_system/urls.py
from django.contrib import admin
from django.urls import path, include # Import include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('api.urls')), # Include your API app's URLs here
]