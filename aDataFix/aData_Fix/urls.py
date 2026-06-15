from django.urls import path
from . import views

urlpatterns = [
    # CONNECTION
    path('', views.db_login_view, name='db_login'),
    path('login-alt/', views.db_login_view, name='db_login_alt'),
    path('select/', views.db_select_view, name='db_select'),
    path('seznam/', views.table_list_view, name='table_list'),
    path('seznam/export-db/', views.export_db_view, name='export_db'),
    path('odpojit/', views.disconnect_view, name='disconnect'),
    path('konzole/', views.sql_console_view, name='sql_console'),

    # TABLE OPERATIONS
    path('tabulka/<str:table_name>/', views.table_data_view, name='table_data'),
    path('tabulka/<str:table_name>/struktura/', views.table_structure_view, name='table_structure'),
    path('tabulka/<str:table_name>/smazat/', views.drop_table_view, name='drop_table'),
    path('tabulka/<str:table_name>/export/', views.export_table_view, name='export_table'),
    path('tabulka/<str:table_name>/import/', views.table_import_view, name='table_import'),
    path('tabulka/<str:table_name>/hromadne-smazani/', views.bulk_delete_view, name='bulk_delete'),
    path('tabulka/<str:table_name>/pridat-radek/', views.table_edit_view, name='table_edit'),
    path('nova-tabulka/', views.table_create_view, name='table_create'),    

    
    # DATA MANIPULATION
    path('tabulka/<str:table_name>/smazat-zaznam/<path:pk_value>/', views.delete_record_view, name='delete_record'),
    path('tabulka/<str:table_name>/upravit-zaznam/<path:pk_value>/', views.table_edit_view, name='table_edit_pk'),

    # COLUMNS AND INDEXES
    path('tabulka/<str:table_name>/pridat-sloupec/', views.add_column_view, name='add_column'),
    path('tabulka/<str:table_name>/smazat-sloupec/<str:column_name>/', views.drop_column_view, name='drop_column'),
    path('tabulka/<str:table_name>/sloupec/<str:column_name>/indexy/', views.column_index_view, name='column_index'),
    path('tabulka/<str:table_name>/sloupec/<str:column_name>/cizi-klice/', views.column_foreign_keys_view, name='column_foreign_keys'),


       
]