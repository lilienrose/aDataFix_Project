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

# djang_adminer/views.py (OPRAVENÁ VERZE)
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.safestring import mark_safe
from django.db import transaction
from django.contrib.auth.decorators import user_passes_test

import csv
import socket
from datetime import datetime
from io import TextIOWrapper


from .forms import (
    ColumnForm, DBLoginForm, SQLConsoleForm, 
    DynamicRecordForm, TableCreateForm, ImportForm 
)
from .db_connector import DBConnector

def get_connector(request):
    if hasattr(request, '_cached_conn'):
        return request._cached_conn

    data = request.session.get('db_connection')
    if data:
        conn = DBConnector(
            host=data['host'], 
            user=data['user'], 
            password=data['password'], 
            database=data.get('database'),
            port=data.get('port')
        )

        if not hasattr(conn, 'connection') or conn.connection is None:
            conn.connect() 

        request._cached_conn = conn
        return conn

    return None

def connection_required(view_func):
    """Dekorátor pro ověření, zda je uživatel připojen."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('db_connection'):
            messages.warning(request, "Pro přístup k této sekci se musíte nejprve připojit.")
            return redirect('db_login') 
        return view_func(request, *args, **kwargs)
    return wrapper



def _get_primary_key_column(col_struct, structure):
    """Dynamicky získá název sloupce PK na základě hlaviček."""
    key_index = -1 
    
    try:
        key_index = col_struct.index('Key') 
    except ValueError:
        return None

    if key_index != -1:
        for col_info in structure:
            if len(col_info) > key_index and col_info[key_index] == 'PRI':
                return col_info[0]
                
    return None


def _get_instance_data(connector, table_name, pk_column, pk_value):
    """Získá data jednoho záznamu podle PK."""
    query = f"SELECT * FROM `{table_name}` WHERE `{pk_column}` = %s LIMIT 1"
    columns, data, errors = connector.execute_query(query, params=[pk_value])
    
    if data and columns:
        return dict(zip(columns, data[0]))
    return {}



def db_login_view(request):
    """Připojení k DB serveru (db_login.html)"""
    if request.method == 'POST':
        form = DBLoginForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            port = data.get('port')
            
            connector = DBConnector(data['host'], data['user'], data['password'], data.get('database'), port=port)
            
            success, error_msg = connector.connect()
            
            if success:
                request.session['db_connection'] = data
                messages.success(request, f"Úspěšně připojeno k {data['host']}:{port if port else 'default'}")
                if data.get('database'):
                    return redirect('table_list')
                else:
                    return redirect('db_select') 
            else:
                messages.error(request, error_msg)
                return render(request, 'aDataFix/db_login.html', {'form': form})
    else:
        if get_connector(request):
             return redirect('table_list')
        form = DBLoginForm()
    
    # SPRÁVNÁ CESTA
    return render(request, 'aDataFix/db_login.html', {'form': form})

@connection_required
def disconnect_view(request):
    """Odpojení a smazání session."""
    if 'db_connection' in request.session:
        del request.session['db_connection']
        messages.info(request, "Odpojeno od databáze.")
    return redirect('db_login')

@connection_required
def table_list_view(request):
    """Zobrazí seznam tabulek a pohledů (table_list.html)"""
    connector = get_connector(request)
    columns, all_objects, errors = connector.get_tables()
    
    tables, views = [], []
    if all_objects:
        for obj in all_objects:
            if obj[1] == 'BASE TABLE': 
                tables.append(obj[0])
            elif obj[1] == 'VIEW':
                views.append(obj[0])

    context = {
        'tables': tables,
        'views': views,
        'errors': errors,
        'db_config': connector.database or "(Není vybrána DB)"
    }
    return render(request, 'aDataFix/table_list.html', context)


@connection_required
def table_data_view(request, table_name):
    connector = get_connector(request)
    res_tables = connector.get_tables()
    raw_table_rows = res_tables[1] if len(res_tables) > 1 else []
    all_tables_list = [row[0] for row in raw_table_rows]
    PAGE_SIZE_DEFAULT = 50 
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', PAGE_SIZE_DEFAULT))
    except ValueError:
        page = 1
        page_size = PAGE_SIZE_DEFAULT
        
    page = max(1, page) 
    

    col_struct, structure, err_struct = connector.get_table_structure(table_name)
    
    if structure is None or err_struct:
        messages.error(request, f"Nepodařilo se načíst strukturu tabulky '{table_name}'. Důvod: {err_struct[0] if err_struct else 'Tabulka neexistuje nebo chyba oprávnění.'}")
        return redirect('table_list')


    total_rows = 0
    total_pages = 1
    pagination_range = range(1, 2) 
    

    count_query = f"SELECT COUNT(*) FROM `{table_name}`"
    _, count_result, count_errors = connector.execute_query(count_query)
    
    if count_result and not count_errors:
        try:
            total_rows = int(count_result[0][0])
        except (ValueError, IndexError):
            pass 
            
    if total_rows > 0:
        total_pages = (total_rows + page_size - 1) // page_size
        page = min(page, total_pages) 
        
        offset = (page - 1) * page_size
        
        sql_query = f"SELECT * FROM `{table_name}` LIMIT {page_size} OFFSET {offset}"
        
        start_page = max(1, page - 9)
        end_page = min(total_pages, page + 9)
        pagination_range = range(start_page, end_page + 1)
        
    else:
        sql_query = f"SELECT * FROM `{table_name}` LIMIT 0"
        
    columns, data_rows, errors = connector.execute_query(sql_query) 
        
    pk_column = None
    pk_index = -1
  
    pk_column = _get_primary_key_column(col_struct, structure)

    fk_cols, fk_data, fk_errors = connector.get_foreign_keys(table_name)
    trigger_cols, trigger_data, trigger_errors = connector.get_triggers(table_name)
    
    
    if pk_column and columns:
        try:
            pk_index = columns.index(pk_column)
        except ValueError:
            pk_index = -1


    processed_data_for_template = [] 
    
    if data_rows: 
        pk_available = pk_index != -1
        
        for row in data_rows:
            pk_value_for_url = None
            if pk_available:
                pk_value_for_url = row[pk_index]
            

            processed_data_for_template.append({
                'row_values': row,                  
                'pk_value_for_url': pk_value_for_url,
            })

    context = {
        'table_name': table_name,
        'sql_query': sql_query,
        'columns': columns,
        'data': data_rows, 
        'structure': structure,
        'structure_cols': col_struct,
        'pk_column': pk_column,
        'pk_index': pk_index, 
        'errors': errors or err_struct,
        'fk_cols': fk_cols,
        'fk_data': fk_data,
        'trigger_cols': trigger_cols,
        'trigger_data': trigger_data,
        'total_rows': total_rows,
        'total_pages': total_pages,
        'page': page,
        'page_size': page_size,
        'pagination_range': pagination_range,
        'data_rows_processed': processed_data_for_template, 
        'all_tables': all_tables_list,
    }
    return render(request, 'aDataFix/table_data.html', context)

@connection_required
def sql_console_view(request):
    connector = get_connector(request)
    columns, data, errors = None, None, None
    form = SQLConsoleForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        query = form.cleaned_data['query']
        columns, data, errors = connector.execute_query(query)
        
        if errors:
            first_msg = str(errors[0])
            
            if "Úspěch|" in first_msg:
                try:
                    count = first_msg.split('|')[-1]
                    query_upper = query.upper()
                    if any(cmd in query_upper for cmd in ["CREATE", "DROP", "ALTER"]):
                        msg = "Struktura databáze byla úspěšně aktualizována."
                    else:
                        msg = f"Příkaz byl úspěšně proveden. Počet ovlivněných řádků: {count}"
                except:
                    msg = "Příkaz byl úspěšně proveden."
                
                messages.success(request, msg)
            else:
                import re
                if "1048" in first_msg or "cannot be null" in first_msg:
                    col = re.search(r"Column '(\w+)'", first_msg)
                    clean_msg = f"Pole '{col.group(1) if col else 'neznámé'}' musí být vyplněno."
                elif "1452" in first_msg:
                    clean_msg = "Chyba vazby: Odkazované ID v jiné tabulce neexistuje."
                elif "1062" in first_msg:
                    clean_msg = "Záznam již existuje (duplicita)."
                elif "already exists" in first_msg.lower():
                    clean_msg = "Tento objekt (tabulka nebo trigger) již v databázi existuje."
                elif "1451" in first_msg:
                    clean_msg = "Záznam nelze odstranit, protože je na něj vázán jiný objekt."
                else:
                    clean_msg = first_msg
                
                messages.error(request, mark_safe(f"CHYBA: {clean_msg}"))
        
        elif not columns and not data:
            messages.success(request, "Dotaz byl úspěšně proveden.")
        
    context = {
        'form': form,
        'columns': columns,
        'data': data,
        'errors': errors
    }
    return render(request, 'aDataFix/sql_console.html', context)



from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.safestring import mark_safe


@connection_required
def table_edit_view(request, table_name, pk_value=None):
    """
    Zpracovává GET pro zobrazení formuláře pro vložení/editaci a POST pro uložení dat.
    """
    connector = get_connector(request)

    if not hasattr(connector, 'connection') or connector.connection is None:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba: Nelze se připojit k databázi. {error_msg}")
            return redirect('table_list')
    
    col_struct, structure, errors = connector.get_table_structure(table_name)
    
    if errors:
        messages.error(request, f"Chyba při načítání struktury tabulky: {errors[0]}")
        return redirect('table_data', table_name=table_name)

    pk_column_name = _get_primary_key_column(col_struct, structure)
    is_new_record = pk_value is None
    initial_data = {} 


    if not is_new_record and pk_column_name:
        query = f"SELECT * FROM `{table_name}` WHERE `{pk_column_name}` = %s"
        cols, data, q_errors = connector.execute_query(query, params=(pk_value,))
        
        if q_errors:
            messages.error(request, f"Chyba při načítání záznamu: {q_errors[0]}")
            return redirect('table_data', table_name=table_name)
            
        if data:
            row_data = []
            for i, val in enumerate(data[0]):
                col_type = str(structure[i][1]).lower()
                
                if val is None:
                    row_data.append('') 
                
                elif 'datetime' in col_type:
                    if hasattr(val, 'isoformat'):
                        row_data.append(val.isoformat()[:16])
                    else:
                        row_data.append(str(val).replace(' ', 'T')[:16])
                
                elif 'date' in col_type and 'datetime' not in col_type:
                    if hasattr(val, 'strftime'):
                        row_data.append(val.strftime('%Y-%m-%d'))
                    else:
                        row_data.append(str(val)[:10])
                
                elif 'tinyint(1)' in col_type or 'bool' in col_type:
                    row_data.append("1" if val else "0")
                else:
                    row_data.append(str(val)) 
            
            initial_data = dict(zip(cols, row_data))
        else:
            messages.warning(request, f"Záznam s klíčem '{pk_value}' nebyl nalezen.")
            return redirect('table_data', table_name=table_name)
            

    if request.method == 'POST':
        postdata = request.POST.copy()
        for field_name in postdata:
            val = postdata.get(field_name)
            if val and isinstance(val, str) and 'T' in val and len(val) <= 19:
                new_val = val.replace('T', ' ')
                if len(new_val) == 16:
                    new_val += ':00'
                postdata[field_name] = new_val
        form = DynamicRecordForm(postdata, structure=structure, pk_name=pk_column_name, initial_data=initial_data)
        
        if form.is_valid():
            cols_or_updates = []
            params = []
            valid_column_names = [col[0] for col in structure]            

            for field_name, value in form.cleaned_data.items():
                if field_name not in valid_column_names:
                    continue

                is_empty = value is None or (isinstance(value, str) and not value.strip())

                if is_new_record and is_empty:
                    print(f"DEBUG: Vynechávám sloupec {field_name}, aby zasáhl DEFAULT v DB")
                    continue
                sql_value = value if value != '' else None 
                
                if is_new_record:
                    cols_or_updates.append(f"`{field_name}`")
                    params.append(sql_value)
                else:
                    if field_name != pk_column_name:
                        cols_or_updates.append(f"`{field_name}` = %s")
                        params.append(sql_value)
            
            if is_new_record:
                placeholders = ", ".join(["%s"] * len(cols_or_updates))
                columns_str = ", ".join(cols_or_updates)
                query = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"
            else:
                update_str = ", ".join(cols_or_updates)
                query = f"UPDATE `{table_name}` SET {update_str} WHERE `{pk_column_name}` = %s"
                params.append(pk_value) 
            
            _, _, q_errors = connector.execute_query(query, params=tuple(params)) 

            if q_errors:
                first_error = q_errors[0]
            
            if first_error.startswith("Úspěch|"):
                action = "vložen" if is_new_record else "aktualizován"
                messages.success(request, f"Záznam byl úspěšně {action}.")
                return redirect('table_data', table_name=table_name)
            else:
                
                if "1048" in first_error or "cannot be null" in first_error:
                    import re
                    column_match = re.search(r"Column '(\w+)'", first_error)
                    column_name = column_match.group(1) if column_match else "neznámé"
                    msg = f"Chyba: Pole '{column_name}' musí být vyplněno."
                elif "1452" in first_error or "foreign key constraint fails" in first_error:
                    msg = "Chyba: Vybraná související položka (např. firma) neexistuje v databázi. Vyberte prosím platnou hodnotu ze seznamu."
                elif "1062" in first_error or "Duplicate entry" in first_error:
                    msg = "Tento záznam již v databázi existuje (duplicitní hodnota)."
                else:
                    msg = f"Chyba při ukládání: {first_error}"
                
                messages.error(request, mark_safe(msg))
        else:
            messages.error(request, "Dotaz nebyl proveden.")
            
    else:
        form = DynamicRecordForm(structure=structure, pk_name=pk_column_name, initial_data=initial_data)

    context = {
        'form': form,
        'table_name': table_name,
        'pk_value': pk_value,
        'is_new_record': is_new_record
    }
    return render(request, 'aDataFix/table_edit.html', context)
@connection_required
def table_create_view(request):
    """Vytvoření nové tabulky (table_create.html)"""
    connector = get_connector(request)
    form = TableCreateForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        
        table_name = data['table_name'].strip('`') 
        
        column_definitions = []
        primary_keys = []
        
        for i in range(1, 4):
            col_name = data.get(f'col{i}_name')
            
            if not col_name:
                continue
                
            col_name = col_name.strip('`')
            
            col_type = data.get(f'col{i}_type')
            is_pk = data.get(f'col{i}_pk')
            is_nn = data.get(f'col{i}_nn')
            is_ai = data.get(f'col{i}_ai')
            

            definition = f"`{col_name}` {col_type}"
            
            if is_nn:
                definition += " NOT NULL"
            if is_ai:
                definition += " AUTO_INCREMENT"
            
            column_definitions.append(definition)
            
            if is_pk:
                primary_keys.append(f"`{col_name}`")

        if primary_keys:
            column_definitions.append(f"PRIMARY KEY ({', '.join(primary_keys)})")

        if not column_definitions:
            messages.error(request, "Tabulka musí obsahovat alespoň jeden sloupec.")
            return render(request, 'aDataFix/table_create.html', {'form': form, 'db_config': connector.database or "(Není vybrána DB)"})
        
        
        columns_sql = ',\n    '.join(column_definitions)
        
        create_query = (
            f"CREATE TABLE `{table_name}` (\n    {columns_sql}\n) "
            f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )

        columns, data_result, errors = connector.execute_query(create_query)
        
        is_success = False
        
        if errors:
            first_error = errors[0]
            
            if first_error.startswith("Úspěch|"):
                is_success = True
            else:
                messages.error(request, mark_safe(f"Chyba při vytváření tabulky: {first_error}<br>Použitý dotaz: <code>{create_query}</code>"))
        else:
            is_success = True
        
        
        if is_success:
            messages.success(request, f"Tabulka '{table_name}' byla úspěšně vytvořena.")
            return redirect('table_list')
            
    context = {'form': form, 'db_config': connector.database or "(Není vybrána DB)"}
    return render(request, 'aDataFix/table_create.html', context)



@connection_required
def export_table_view(request, table_name):
    """Exportuje data tabulky do čistého CSV souboru."""
    connector = get_connector(request)
    
    if not connector or not connector.database:
        messages.error(request, "Pro export je vyžadováno aktivní připojení k databázi.")
        return redirect('table_list')

    # Načtení dat
    sql_query = f"SELECT * FROM `{table_name}`"
    columns, data_rows, data_errors = connector.execute_query(sql_query) 
    
    if data_errors:
        messages.error(request, f"Chyba při načítání dat: {data_errors[0]}")
        return redirect('table_data', table_name=table_name)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"{table_name}_{connector.database}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    
    writer.writerow(columns)
    
    if data_rows:
        for row in data_rows:
            writer.writerow(row)

    return response

# djang_adminer/views.py

@connection_required
def table_structure_view(request, table_name):
    """Zobrazí strukturu tabulky (sloupce, typy, klíče)."""
    connector = get_connector(request)
   
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')

    col_struct, structure, err_struct = connector.get_table_structure(table_name)
    
    index_cols, index_data, err_index = connector.get_table_indexes(table_name)
    fk_cols, fk_data, err_fk = connector.get_foreign_keys(table_name)
    

    if structure is None or err_struct:
        error_detail = err_struct[0] if err_struct else "Neznámá chyba nebo chybí oprávnění."
        messages.error(request, mark_safe(f"Nepodařilo se načíst strukturu tabulky '{table_name}'. Důvod: {error_detail}"))
        return redirect('table_list')
        
    context = {
        'table_name': table_name,
        'structure': structure,
        'structure_cols': col_struct,
        'index_data': index_data,
        'index_cols': index_cols,
        'fk_data': fk_data,
        'fk_cols': fk_cols,
        'errors': err_struct or err_index or err_fk,
        'db_config': connector.database or "(Není vybrána DB)"
    }
    
    return render(request, 'aDataFix/table_structure.html', context)

@connection_required
def column_index_view(request, table_name, column_name):
    """Zobrazí detailní indexy pro konkrétní sloupec."""
    connector = get_connector(request)
    

    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')


    index_cols, index_data, errors = connector.get_table_indexes(table_name)
    
    filtered_data = []
    if index_data and index_cols:
        try:
            col_index = index_cols.index('Column_name')
            for row in index_data:
                if row[col_index] == column_name:
                    filtered_data.append(row)
        except ValueError:
            errors = (f"Chyba: Index sloupce 'Column_name' nebyl nalezen v metadatech.",)


    context = {
        'table_name': table_name,
        'column_name': column_name,
        'data_title': f"Indexy sloupce '{column_name}'",
        'data_cols': index_cols,
        'data': filtered_data,
        'errors': errors,
        'db_config': connector.database or "(Není vybrána DB)"
    }
    return render(request, 'aDataFix/column_detail.html', context)


@connection_required
def column_foreign_keys_view(request, table_name, column_name):
    """Zobrazí detailní cizí klíče pro konkrétní sloupec."""
    connector = get_connector(request)
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')
   
    fk_cols, fk_data, errors = connector.get_foreign_keys(table_name)

    filtered_data = []
    if fk_data and fk_cols:
        col_index = 0 
        for row in fk_data:
            if row[col_index] == column_name:
                filtered_data.append(row)

    context = {
        'table_name': table_name,
        'column_name': column_name,
        'data_title': f"Cizí klíče sloupce '{column_name}'",
        'data_cols': fk_cols,
        'data': filtered_data,
        'errors': errors,
        'db_config': connector.database or "(Není vybrána DB)"
    }
    return render(request, 'aDataFix/column_detail.html', context)



@connection_required
def drop_column_view(request, table_name, column_name):
    """
    Zpracuje smazání sloupce pomocí ALTER TABLE DROP COLUMN.
    Očekává column_name jako argument z URL (ne z POST).
    """
    connector = get_connector(request)
    
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')
    

    if not column_name:
        messages.error(request, "Nebyl zadán název sloupce pro smazání.")
        return redirect('table_structure', table_name=table_name)
            
 
    query = f"ALTER TABLE `{table_name}` DROP COLUMN `{column_name}`"
    

    _, _, q_errors = connector.execute_query(query)

    is_ddl_success = False
    error_message = None
    
    if not q_errors:
        is_ddl_success = True
    else:
        first_error = q_errors[0]
        

        if first_error.startswith("Úspěch|") or "nebyly ovlivněny žádné řádky" in first_error:
            is_ddl_success = True 
        
        else:
            error_message = first_error

    
    if is_ddl_success:
        messages.success(request, f"Sloupec '{column_name}' byl úspěšně smazán z tabulky '{table_name}'.")
    else:
        messages.error(request, mark_safe(f"Chyba při mazání sloupce: {error_message}<br>Použitý dotaz: <code>{query}</code>"))

    return redirect('table_structure', table_name=table_name)

@connection_required
def add_column_view(request, table_name):
    """
    Zobrazí formulář pro přidání sloupce a zpracuje ALTER TABLE ADD COLUMN.
    """
    connector = get_connector(request)
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')

    if request.method == 'POST':
        form = ColumnForm(request.POST)

        if form.is_valid():
            col_data = form.cleaned_data
            col_name = f"`{col_data['column_name']}`"
            data_type = col_data['data_type'].upper()
            default_val = col_data['default_value']
            length = col_data['length']
            types_without_length = ('TEXT', 'MEDIUMTEXT', 'LONGTEXT', 'DATE', 'DATETIME', 'TIME', 'BLOB', 'MEDIUMBLOB', 'LONGBLOB', 'FLOAT', 'DOUBLE')
            
            if data_type in types_without_length:
                col_definition = data_type
            elif length:
                col_definition = f"{data_type}({length})"
            else:
                col_definition = data_type

           
            col_definition += " NULL" if col_data['is_null'] else " NOT NULL"

  
            if default_val:

                sql_default = default_val.replace('T', ' ')
                col_definition += f" DEFAULT '{sql_default}'"
            elif not col_data['is_null'] and data_type == 'DATETIME':
      
                col_definition += " DEFAULT CURRENT_TIMESTAMP"

            if col_data['is_auto_increment'] and data_type in ('INT', 'BIGINT', 'SMALLINT', 'TINYINT'):
                col_definition += " AUTO_INCREMENT"
            
            if col_data['is_primary'] or col_data['is_auto_increment']:
                 messages.warning(request, "Nastavení PK/AI při přidání sloupce je složitá operace. Tato funkce přidá sloupec se základním typem.")


            query = f"ALTER TABLE `{table_name}` ADD COLUMN {col_name} {col_definition}"
            _, _, q_errors = connector.execute_query(query)
            
            is_ddl_success = False
            error_message = None
            
            if not q_errors:
                is_ddl_success = True
            else:
                first_error = q_errors[0]
                if first_error.startswith("Úspěch|") or "nebyly ovlivněny žádné řádky" in first_error:
                    is_ddl_success = True 
                else:
                    error_message = first_error

            if is_ddl_success:
                messages.success(request, f"Sloupec '{col_data['column_name']}' byl úspěšně přidán.")
                return redirect('table_structure', table_name=table_name)
            else:
                messages.error(request, mark_safe(f"Chyba: {error_message}<br>Dotaz: <code>{query}</code>"))
        else:
            messages.error(request, "Chyba ve formuláři. Zkontrolujte prosím všechna pole.")
            
    else:
        form = ColumnForm()

    context = {
        'form': form,
        'table_name': table_name,
        'db_config': connector.database or "(Není vybrána DB)"
    }
    return render(request, 'aDataFix/add_column.html', context)

@connection_required
def table_import_view(request, table_name):
    """Zobrazí formulář pro import a zpracuje nahrání souboru CSV."""
    connector = get_connector(request)
    
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')

    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            try:
                try:
                    text_file = TextIOWrapper(csv_file.file, encoding='utf-8')
                    text_file.read(1)
                    text_file.seek(0)
                except UnicodeDecodeError:
                    csv_file.seek(0)
                    text_file = TextIOWrapper(csv_file.file, encoding='cp1250')

                sample = text_file.read(2048)
                text_file.seek(0)
                delimiter = ';' if ';' in sample else ','
                csv_reader = csv.reader(text_file, delimiter=delimiter)
                
                rows_to_insert = []
                header = None
                
                for row in csv_reader:
                    if not row or not any(field.strip() for field in row):
                        continue
                    
                    first_col = row[0].strip().lower()
                    if (first_col.startswith('--') or first_col.startswith('/*') or 
                        first_col.startswith('insert into') or first_col.startswith('create table') or
                        first_col.startswith(')') or 'engine=' in first_col or 'primary key' in first_col):
                        continue
                    
                    if header is None:
                        header = [h.strip('`"\' ') for h in row]
                        continue
                        
                    if len(row) == len(header):
                        rows_to_insert.append(row)
                
                if not header or not rows_to_insert:
                    messages.error(request, "Soubor neobsahuje žádná platná data k importu.")
                    return redirect('table_data', table_name=table_name)

                _, structure, _ = connector.get_table_structure(table_name)
                existing_cols = [col[0].lower() for col in structure]
                
                for col_name in header:
                    if col_name.lower() not in existing_cols:
                        alter_query = f"ALTER TABLE `{table_name}` ADD COLUMN `{col_name}` TEXT NULL"
                        connector.execute_query(alter_query)

                inserted_rows = 0
                with transaction.atomic():
                    cols_str = ", ".join([f"`{col}`" for col in header])
                    placeholders = ", ".join(["%s"] * len(header))
                    query = f"INSERT INTO `{table_name}` ({cols_str}) VALUES ({placeholders})"
                    
                    for row in rows_to_insert:
                        clean_row = [val.strip() if val.strip() != '' else None for val in row]
                        row_count, _, q_errors = connector.execute_query(query, clean_row)
                        
                        if q_errors and not str(q_errors[0]).startswith("Úspěch"):
                             raise Exception(f"Chyba u řádku {row}: {q_errors[0]}")
                        
                        try:
                            inserted_rows += int(q_errors[0].split('|')[1]) if q_errors else 1
                        except:
                            inserted_rows += 1
                             
                messages.success(request, f"Úspěšně importováno {inserted_rows} řádků. Struktura byla případně upravena.")
                return redirect('table_data', table_name=table_name)

            except Exception as e:
                messages.error(request, f"Chyba při zpracování importu: {e}")
                
        else:
            messages.error(request, "Chyba ve formuláři.")
    else:
        form = ImportForm()

    return render(request, 'aDataFix/import.html', {'form': form, 'table_name': table_name})

@connection_required
def delete_record_view(request, table_name, pk_value):
    """
    Smaže jeden záznam z tabulky podle primárního klíče (DELETE dotaz).
    Používá dynamické zjištění PK a bezpečné zpracování dotazu.
    """
    connector = get_connector(request)

    success, error_msg = connector.connect()
    if not success:
        messages.error(request, f"Chyba: Nelze se připojit k databázi. {error_msg}")
        return redirect('table_list') 
    
    col_struct, structure, errors = connector.get_table_structure(table_name)
    
    if errors:
        messages.error(request, f"Chyba při načítání struktury tabulky: {errors[0]}")
        return redirect('table_data', table_name=table_name)

    pk_column_name = _get_primary_key_column(col_struct, structure)

    if not pk_column_name:
        messages.error(request, f"Nelze smazat záznam. Tabulka '{table_name}' nemá definován primární klíč (PK).")
        return redirect('table_data', table_name=table_name)

    
    if pk_value is None or str(pk_value).strip() == '':
        messages.error(request, "Chyba: Hodnota klíče pro smazání je neplatná.")
        return redirect('table_data', table_name=table_name)
    

    pk_value_safe = pk_value
    try:
  
        pk_value_safe = int(pk_value)
    except ValueError:
        pass 
    
    query = f"DELETE FROM `{table_name}` WHERE `{pk_column_name}` = %s"
    
    print(f"DEBUG DELETE: Dotaz: {query}, Hodnota PK: {pk_value_safe} (Typ: {type(pk_value_safe)})")
    
  
    _, _, q_errors = connector.execute_query(query, params=(pk_value_safe,))


    if q_errors:
        first_error = q_errors[0]
        
        if first_error.startswith("Úspěch|"):
            try:
                row_count = int(first_error.split('|')[1])
            except (IndexError, ValueError):
                row_count = 1 
                
            if row_count > 0:
                messages.success(request, f"Záznam s klíčem '{pk_value}' byl úspěšně smazán. Řádků ovlivněno: {row_count}")
            else:
                messages.warning(request, f"Chyba při mazání záznamu: Záznam s klíčem '{pk_value}' nebyl nalezen (0 ovlivněných řádků).")
        else:
            messages.error(request, mark_safe(f"Chyba při mazání záznamu: {first_error}<br>Použitý dotaz: <code>{query}</code>"))
    else:
        messages.warning(request, f"Záznam s klíčem '{pk_value}' nebyl nalezen nebo smazán (0 ovlivněných řádků).")

    return redirect('table_data', table_name=table_name)

@connection_required
def bulk_delete_view(request, table_name):
    """
    Zpracuje hromadné smazání vybraných záznamů na základě jejich PK.
    """
    if request.method != 'POST':
        return redirect('table_data', table_name=table_name)
        
    connector = get_connector(request)
    
    if not connector.connection:
        success, error_msg = connector.connect()
        if not success:
            messages.error(request, f"Chyba připojení: {error_msg}")
            return redirect('table_list')

    col_struct, structure, errors = connector.get_table_structure(table_name)
    
    if errors:
        messages.error(request, f"Chyba při načítání struktury tabulky: {errors[0]}")
        return redirect('table_data', table_name=table_name)

    pk_column = _get_primary_key_column(col_struct, structure)

    if not pk_column:
        messages.error(request, f"Nelze provést hromadné smazání. Tabulka '{table_name}' nemá definovaný primární klíč (PK).")
        return redirect('table_data', table_name=table_name)

    selected_pks = request.POST.getlist('record_pk')
    
    if not selected_pks:
        messages.warning(request, "Nebyly vybrány žádné záznamy ke smazání.")
        return redirect('table_data', table_name=table_name)


    selected_pks_int = []
    try:

        selected_pks_int = [int(pk) for pk in selected_pks if str(pk).isdigit()]
        
        if not selected_pks_int:
             messages.error(request, "Všechny vybrané hodnoty klíče byly neplatné nebo nebyly vybrány (vyžaduje se číslo).")
             return redirect('table_data', table_name=table_name)
             
    except ValueError:
        messages.error(request, "Chyba: Jedna nebo více vybraných hodnot klíče není platné číslo.")
        return redirect('table_data', table_name=table_name)

    placeholders = ', '.join(['%s'] * len(selected_pks_int))

    query = f"DELETE FROM `{table_name}` WHERE `{pk_column}` IN ({placeholders})"
    
    try:

        deleted_count, _, q_errors = connector.execute_query(query, params=selected_pks_int)

 
        if q_errors:
            first_error = q_errors[0]
            
            if first_error.startswith("Úspěch|"):
                 try:
                    deleted_count = int(first_error.split('|')[1])
                 except (IndexError, ValueError):
                    deleted_count = 0
            else:
                 # Skutečná SQL chyba
                 messages.error(request, mark_safe(f"Chyba při mazání: {first_error}<br>Použitý dotaz: <code>{query}</code>"))
                 return redirect('table_data', table_name=table_name)

        
        if deleted_count > 0:
            messages.success(request, f"Úspěšně smazáno {deleted_count} záznamů.")
        else:
            messages.warning(request, f"Dotaz proběhl, ale nebyly smazány žádné záznamy (PK nenalezeno). Použitý dotaz: <code>{query}</code>")
            
    except Exception as e:
        messages.error(request, f"Kritická chyba databáze při mazání: {e}")

    return redirect('table_data', table_name=table_name)


@connection_required
def drop_table_view(request, table_name):
    """
    Smaže celou tabulku (DROP TABLE).
    Očekává se, že bude volána přes POST (např. z formuláře s potvrzením).
    """
    connector = get_connector(request)

    if request.method != 'POST':
        messages.warning(request, "Pro smazání tabulky je vyžadována metoda POST (potvrzení formuláře).")
        return redirect('table_data', table_name=table_name)

    query = f"DROP TABLE `{table_name}`"

    try:
        _, _, q_errors = connector.execute_query(query)
        
        deleted_count = 0 
        
        if q_errors:
            first_error = q_errors[0]
            
            if first_error.startswith("Úspěch|"):
                messages.success(request, f"Tabulka '{table_name}' byla úspěšně smazána.")
                connector.close() 
            elif 'nebyly ovlivněny žádné řádky' in first_error:
                 messages.success(request, f"Tabulka '{table_name}' byla úspěšně smazána.")
                 connector.close()
            else:
                messages.error(request, mark_safe(f"Chyba při mazání tabulky: {first_error}<br>Použitý dotaz: <code>{query}</code>"))
        else:
             messages.success(request, f"Tabulka '{table_name}' byla úspěšně smazána (žádná návratová zpráva).")
             connector.close()
             
    except Exception as e:
        messages.error(request, f"Kritická chyba při mazání tabulky: {e}")


    response = redirect('table_list')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response


@connection_required
def db_select_view(request):
    """Zobrazí seznam všech dostupných databází na serveru a umožní výběr."""
    connector = get_connector(request)
    query = "SHOW DATABASES" 
    _, db_data, errors = connector.execute_query(query)
    
    if errors:
        messages.error(request, f"Chyba při načítání seznamu databází: {errors[0]}")
        return redirect('disconnect')
    
    system_dbs = ['information_schema', 'performance_schema', 'mysql', 'sys']

    db_names = [row[0] for row in db_data if row[0] not in system_dbs]
    
    request.session['db_list'] = db_names

    if request.method == 'POST':
        selected_db = request.POST.get('selected_db')
        
        if selected_db and selected_db in db_names:
            connection_data = request.session.get('db_connection')
            
            connection_data['database'] = selected_db 
            request.session['db_connection'] = connection_data
            
            messages.success(request, f"Úspěšně připojeno k databázi '{selected_db}'.")
            return redirect('table_list') 
        else:
            messages.error(request, "Neplatný výběr databáze. Vyberte prosím ze seznamu.")

    context = {
        'db_names': db_names,
    }
    return render(request, 'aDataFix/db_select.html', context)


def resolve_db_host(hosts, port, timeout=1.5):
    """
    Vrátí první host, na který se lze TCP připojit.
    """
    for host in hosts:
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return host
        except Exception:
            continue
    return None

@connection_required
def export_db_view(request):
    connector = get_connector(request)
    
    if not connector:
        messages.error(request, "Relace vypršela, přihlaste se znovu.")
        return redirect('table_list')

    success, error_msg = connector.connect()
    if not success or not connector.connection:
        messages.error(request, f"Nepodařilo se navázat spojení pro export: {error_msg}")
        return redirect('table_list')

    db_name = request.session.get('db_connection', {}).get('database', 'export')

    def generate_csv_stream():
        class Echo:
            def write(self, value):
                return value

        writer = csv.writer(Echo(), delimiter=';', quoting=csv.QUOTE_MINIMAL)
        
        try:
            conn = connector.connection
            cursor = conn.cursor()
            
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                yield f"\n-- TABLE_DATA: {table}\n"
                
                cursor.execute(f"SELECT * FROM `{table}` LIMIT 0")
                columns = [col[0] for col in cursor.description]
                yield writer.writerow(columns)

                cursor.execute(f"SELECT * FROM `{table}`")
                while True:
                    rows = cursor.fetchmany(100) 
                    if not rows:
                        break
                    for row in rows:
                        yield writer.writerow(row)
                
            cursor.close()

        except Exception as e:
            yield f"\n-- CHYBA PŘI GENEROVÁNÍ: {str(e)}\n"
    response = StreamingHttpResponse(generate_csv_stream(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{db_name}_full_backup.csv"'
    response['Cache-Control'] = 'no-cache'
    
    return response