# DJANGADMINER/db_connector.py
from django.db import connections, DatabaseError, ProgrammingError
from django.conf import settings
from django.db.backends.mysql.base import DatabaseWrapper as DBAdapter 
import warnings
from django.db.utils import DatabaseError


DB_CONNECTION_NAME = 'default' 



class DBConnector:
    """Spravuje dynamické připojení a provádění syrových dotazů na databázi."""

    def __init__(self, host=None, user=None, password=None, database=None, port=None, driver='mysql'):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port  
        self.driver_name = driver
        self.connection = None 
        self.Error = DatabaseError


    def connect(self):
        try:
            current_host = self.host if self.host else '127.0.0.1'
            current_port = str(self.port) if self.port else '3306'

            if current_host and ':' in str(current_host):
                try:
                    host_part, port_part = str(current_host).split(':')
                    current_host = host_part
                    current_port = port_part
                except ValueError:
                    pass

            settings_dict = {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': self.database if self.database else '',
                'USER': self.user if self.user else '',
                'PASSWORD': self.password if self.password else '',
                'HOST': current_host,
                'PORT': current_port,
                'TIME_ZONE': None,              
                'CONN_MAX_AGE': 0,              
                'CONN_HEALTH_CHECKS': False,  
                'AUTOCOMMIT': True,
                'OPTIONS': {
                    'connect_timeout': 5,       
                },
            }

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                db_wrapper = DBAdapter(settings_dict) 
                db_wrapper.connect()
                self.connection = db_wrapper 
                
            return True, None
            
        except (DatabaseError, Exception) as e:
            self.connection = None
            error_text = str(e)
            
            if '(2002,' in error_text:
                return False, f"Chyba připojení: Server na {current_host}:{current_port} neodpovídá (je zapnutá MariaDB?)."
            
            if '(2005,' in error_text:
                return False, f"Chyba: Neznámý hostitel '{current_host}'. Zkontrolujte formát IP adresy."
            
            if '(1045,' in error_text:
                return False, "Chyba autentizace: Špatné uživatelské jméno nebo heslo."
            
            if '(1049,' in error_text:
                return False, f"Chyba: Databáze '{self.database}' na tomto serveru neexistuje."
            
            return False, f"Neočekávaná chyba při připojení: {error_text}"    
    def execute_query(self, query, params=None):
        """
        Provede libovolný SQL dotaz (SELECT, DDL, DML) pomocí Django DB API.
        Klíčová oprava: U DDL dotazů (CREATE, DROP) akceptuje row_count=0 jako úspěch.
        Vrací: (sloupce: list, data: list, chyby: list)
        """

        success, error_msg = self.connect()
        if not success:
             return None, None, [f"Chyba: Nelze navázat spojení. {error_msg}"]

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                
                row_count = cursor.rowcount 
                
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    results = cursor.fetchall()
                    return columns, results, None 
                else:
                    if not self.connection.get_autocommit():
                         self.connection.commit()
                         
                    
                    if row_count >= 0:
               
                        if row_count > 0:
             
                            return None, None, [f"Úspěch|{row_count}"] 
                        else:

                            return None, None, ["Úspěch|0"] 
                    
                
                    return None, None, [f"Úspěch|{row_count}"] 
        
        except (DatabaseError, ProgrammingError) as e:
            return None, None, [f"Chyba SQL dotazu ({type(e).__name__}): {e}"]
        
        except Exception as e:
            return None, None, [f"Neočekávaná chyba: {e}"]
    def get_tables(self):
        return self.execute_query("SHOW FULL TABLES WHERE Table_Type IN ('BASE TABLE', 'VIEW')")
    
    def get_table_structure(self, table_name):
        return self.execute_query(f"DESCRIBE `{table_name}`")

    def get_table_indexes(self, table_name):
        if not self.connection or not self.database:
            return None, None, ("Není připojeno k databázi.",)
        query = f"SHOW INDEX FROM `{table_name}`"
        try:
            index_cols, index_data, errors = self.execute_query(query)
            if errors:
                return None, None, errors
            return index_cols, index_data, None
        except Exception as e:
            return None, None, (f"Chyba SQL dotazu: {e}",)
            
    def get_foreign_keys(self, table_name):
        if not self.connection or not self.database:
            return None, None, ("Není připojeno k databázi.",)
        safe_query = f"""
            SELECT 
                kcu.column_name, 
                kcu.referenced_table_name, 
                kcu.referenced_column_name, 
                rc.update_rule, 
                rc.delete_rule
            FROM 
                information_schema.key_column_usage AS kcu
            JOIN 
                information_schema.referential_constraints AS rc 
                ON kcu.constraint_name = rc.constraint_name
            WHERE 
                kcu.table_schema = '{self.database}' AND kcu.table_name = '{table_name}' 
                AND rc.table_name = '{table_name}' AND kcu.referenced_table_name IS NOT NULL;
        """
        fk_cols = ['Sloupec', 'Cílová Tabulka', 'Cílový Sloupec', 'ON UPDATE', 'ON DELETE']
        try:
            cols, fk_data, errors = self.execute_query(safe_query)
            if errors:
                return None, None, errors
            return fk_cols, fk_data, None
        except Exception as e:
            return None, None, (f"Chyba při získávání cizích klíčů: {e}",)
        

    def get_triggers(self, table_name):
        """Získává seznam triggerů pro danou tabulku."""
        
        if not self.connection or not self.database:
            return None, None, ("Není připojeno k databázi.",)
        

        query = f"""
            SELECT 
                trigger_name, 
                event_manipulation, 
                event_object_table, 
                action_timing, 
                action_statement 
            FROM 
                information_schema.TRIGGERS 
            WHERE 
                event_object_schema = '{self.database}' 
                AND event_object_table = '{table_name}';
        """
        
        trigger_cols = ['Název Triggeru', 'Událost', 'Tabulka', 'Kdy', 'Akce (SQL)']
        
        try:
            cols, trigger_data, errors = self.execute_query(query)
            
            if errors:
                if errors[0].startswith("Úspěch|"):
                    return trigger_cols, [], None 
                return None, None, errors
            
            return trigger_cols, trigger_data, None
            
        except Exception as e:
            return None, None, (f"Chyba při získávání triggerů: {e}",)
            
        

    def close(self):
        """Zavře připojení (využíváme Django API)."""
        if self.connection:
             self.connection.close()