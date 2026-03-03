from django.urls import path
from .views import tables_view
from . import views

urlpatterns = [
    path('', views.electricity_view, name='electricity'),
    path('gasolio/', views.gas_view, name='gas'),
    path('working-hours/', views.working_hours_view, name='working_hours'),
    path('tables/', tables_view, name='tables'),
    path('economic/', views.economic_view, name='economic_analysis'),
    path('co2/', views.co2_view, name='co2_analysis')
]
