from django.urls import path
from .views import tables_view
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.electricity_view, name='electricity'),
    path('gasolio/', views.gas_view, name='gas'),
    path('working-hours/', views.working_hours_view, name='working_hours'),
    path('tables/', tables_view, name='tables'),
    path('economic/', views.economic_view, name='economic_analysis'),
    path('co2/', views.co2_view, name='co2_analysis'),
    path('login/', auth_views.LoginView.as_view(template_name='pages/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
