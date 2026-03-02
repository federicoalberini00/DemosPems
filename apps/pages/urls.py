from django.urls import path
from .views import tables_view
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('tables/', tables_view, name='tables'),
]
