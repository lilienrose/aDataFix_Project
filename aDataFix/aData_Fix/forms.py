#------------------------------------------------------------------------------------
#                  INTEGRATION PROCEDURE - aDataFix 
#------------------------------------------------------------------------------------
# 1. What to move and where? (Current Directory Structure)
# views.py -> aDataFix/aData_Fix/views.py (contains db_login_view and app logic)
# forms.py -> aDataFix/aData_Fix/forms.py (forms for table editing/management)
# db_connector.py -> aDataFix/aData_Fix/db_connector.py (manages DB connection layers)
# templates/ -> templates/aDataFix/ (HTML folder moved to root, next to manage.py)
# urls.py -> aDataFix/urls.py (main routing) + aDataFix/aData_Fix/urls.py (app-level)
# templatetags/ -> aDataFix/aData_Fix/templatetags/custom_filters.py (custom filters)
#
# CRITICAL CONFIGURATIONS (The project will not start without these):
# - In the aDataFix/__init__.py file (or at the very top of settings.py), you must include:
#   import pymysql
#   pymysql.install_as_MySQLdb()
# - In settings.py under the TEMPLATES section, set: 'DIRS': [BASE_DIR / 'templates']
# - In settings.py under INSTALLED_APPS, register the app as: 'aDataFix.aData_Fix'
#------------------------------------------------------------------------------------
# 2. How to log into the database interface of the application?
# Host:       127.0.0.1 (for local running MariaDB/MySQL) or the production server IP/domain
# User:       For local host (127.0.0.1) usually "root", for servers use the designated MySQL user
# Password:   The corresponding password for the chosen user (your root password for local MariaDB)
# Database:   Enter the default database name (e.g., divDB). If unknown, it can be selected later.
#------------------------------------------------------------------------------------

# DJANGADMINER/forms.py
from django import forms
from datetime import date, datetime

DATA_TYPES = [
    ('INT', 'INT'),
    ('VARCHAR(255)', 'VARCHAR(255)'),
    ('TEXT', 'TEXT'),
    ('DATE', 'DATE'),
    ('DATETIME', 'DATETIME'),
    ('BOOLEAN', 'BOOLEAN'),
]

class DBLoginForm(forms.Form):
    """Formulář pro připojení k databázovému serveru."""
    host = forms.CharField(label="Host", initial="localhost", max_length=255)
    user = forms.CharField(label="Uživatel", max_length=255)
    password = forms.CharField(widget=forms.PasswordInput, label="Heslo", required=False)
    database = forms.CharField(label="Databáze", required=False, max_length=255)

class SQLConsoleForm(forms.Form):
    """Formulář pro spouštění libovolných SQL dotazů."""
    query = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'class': 'sql-editor'}),
        label="SQL Dotaz",
        initial="SELECT * FROM"
    )

class DynamicRecordForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.structure = kwargs.pop('structure', [])
        self.pk_name = kwargs.pop('pk_name', None)
        self.initial_data = kwargs.pop('initial_data', {}) 
 
        super().__init__(*args, **kwargs)
        
        self._build_dynamic_fields() 
        
        if self.initial_data:
            for field_name, value in self.initial_data.items():
                if field_name in self.fields:
                    self.fields[field_name].initial = value

        if self.pk_name in self.fields and not self.initial_data:
            is_auto_increment = next((True for col in self.structure if col[0] == self.pk_name and len(col) > 6 and 'auto_increment' in str(col[6]).lower()), False)
            if is_auto_increment:
                self.fields[self.pk_name].widget = forms.HiddenInput()
                self.fields[self.pk_name].required = False
                
    def _build_dynamic_fields(self):
        """Dynamicky vytváří pole formuláře na základě struktury tabulky."""
        for col in self.structure:
            field_name = col[0]
            field_type = col[1].lower()
            is_nullable = col[3] == 'YES'

            # Společné nastavení pro všechna pole
            field_kwargs = {
                'label': field_name,
                'required': False, # Pokud je NULL povolen, required bude False
            }

            widget_instance = None

            if 'text' in field_type or 'varchar' in field_type:
                field_class = forms.CharField
                widget_class = forms.Textarea if 'text' in field_type else forms.TextInput
            
            elif 'int' in field_type:
                if 'tinyint(1)' in field_type or 'boolean' in field_type or 'bool' in field_type:
                    # Speciální případ pro boolean/tinyint
                    self.fields[field_name] = forms.ChoiceField(
                        choices=[('', '---------'), (1, 'True'), (0, 'False')],
                        widget=forms.Select(attrs={'class': 'form-control'}),
                        **field_kwargs
                    )
                    continue
                else:
                    field_class = forms.IntegerField
                    widget_class = forms.NumberInput

            elif 'datetime' in field_type:
                field_class = forms.DateTimeField
                widget_instance = forms.DateTimeInput(
                    attrs={'type': 'datetime-local', 'class': 'form-control'},
                    format='%Y-%m-%dT%H:%M'
                )
                field_kwargs.update({
                    'widget': widget_instance,
                    'input_formats': ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
                })
                self.fields[field_name] = field_class(**field_kwargs)
                continue

            elif 'date' in field_type:
                field_class = forms.DateField
                widget_instance = forms.DateInput(
                    attrs={'type': 'date', 'class': 'form-control'},
                    format='%Y-%m-%d'
                )
                field_kwargs['widget'] = widget_instance
            else:
                field_class = forms.CharField
                widget_class = forms.TextInput
            
            # Pokud pole nemá specifický widget (jako datetime), přidáme výchozí s class
            if 'widget' not in field_kwargs:
                field_kwargs['widget'] = widget_class(attrs={'class': 'form-control'})
            
            self.fields[field_name] = field_class(**field_kwargs)
class ColumnForm(forms.Form):
    """Dynamický sub-formulář pro jeden sloupec s Bootstrap styly."""
    

    column_name = forms.CharField(
        label="Název sloupce", 
        max_length=64,
        widget=forms.TextInput(attrs={'class': 'form-control', 'required': True})
    )
    

    data_type = forms.ChoiceField(
        label="Datový typ", 
        choices=DATA_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    

    length = forms.CharField(
        label="Délka/Sada", 
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'např. 255'})
    )
    

    is_primary = forms.BooleanField(
        label="Primární klíč", 
        required=False
    )

    default_value = forms.CharField( 
    label="Výchozí hodnota (i čas)",
    required=False,
    widget=forms.TextInput(attrs={
        'class': 'form-control',
        'type': 'datetime-local'
    })
)

    is_null = forms.BooleanField(
        label="NULL (Povolit)", 
        required=False,
        initial=True
    )
    
    is_auto_increment = forms.BooleanField(
        label="AUTO_INCREMENT", 
        required=False
    )


class TableCreateForm(forms.Form):
    """Hlavní formulář pro vytvoření tabulky."""
    table_name = forms.CharField(label="Název tabulky", max_length=64)
  
    col1_name = forms.CharField(label="Název sloupce 1", max_length=64, initial='id')
    col1_type = forms.ChoiceField(label="Typ 1", choices=DATA_TYPES, initial='INT')
    col1_pk = forms.BooleanField(label="PK 1", required=False, initial=True)
    col1_nn = forms.BooleanField(label="NN 1", required=False, initial=True)
    col1_ai = forms.BooleanField(label="AI 1", required=False, initial=True)


    col2_name = forms.CharField(label="Název sloupce 2", max_length=64, required=False)
    col2_type = forms.ChoiceField(label="Typ 2", choices=DATA_TYPES, required=False)
    col2_pk = forms.BooleanField(label="PK 2", required=False)
    col2_nn = forms.BooleanField(label="NN 2", required=False)
    col2_ai = forms.BooleanField(label="AI 2", required=False)
    
  
    col3_name = forms.CharField(label="Název sloupce 3", max_length=64, required=False)
    col3_type = forms.ChoiceField(label="Typ 3", choices=DATA_TYPES, required=False)
    col3_pk = forms.BooleanField(label="PK 3", required=False)
    col3_nn = forms.BooleanField(label="NN 3", required=False)
    col3_ai = forms.BooleanField(label="AI 3", required=False)

class ImportForm(forms.Form):
    """Formulář pro nahrání souboru CSV pro import."""
    
    csv_file = forms.FileField(
        label="Vyberte CSV soubor",
        help_text="Soubor musí obsahovat data v pořadí odpovídajícím sloupcům tabulky.",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )