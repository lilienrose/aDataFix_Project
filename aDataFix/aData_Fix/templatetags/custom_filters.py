#toto jsou filtry pro aDataFix!

from django import template
from datetime import datetime, date
register = template.Library()

@register.filter
def index(sequence, item):
    """Vrací index prvku v sekvenci. Pokud není nalezen, vrací -1."""
    try:
        return sequence.index(item)
    except ValueError:
        return -1

@register.filter
def get_item_at(value, index):
    """
    Vrátí hodnotu z listu (řádku) na daném indexu.
    Použití: {{ row|get_item_at:pk_index }}
    """
    try:
        return value[index]
    except (IndexError, TypeError):
        return None
    
@register.filter(name='is_datetime')
def is_datetime_check(value): 
    return isinstance(value, (datetime, date))

@register.filter
def get_type_at(structure, index):
    try:
        return str(structure[index][1]).lower()
    except (IndexError, TypeError):
        return ""