# aDataFix

 **aDataFix** – webová aplikace postavená na frameworku Django, která slouží pro rychlou správu, prohlížení a opravu databázových tabulek přímo přes prohlížeč.

<img width="1328" height="942" alt="image" src="https://github.com/user-attachments/assets/4585e6f2-5f32-450d-a6d0-c7e474593613" />


<img width="1328" height="583" alt="image" src="https://github.com/user-attachments/assets/42c283b0-1ebb-4777-9439-0b528be36f08" />


## Zprovoznění projektu:

Postupujte podle těchto kroků:

### 1. Naklonujte si repozitář
git clone https://github.com/Butterfliee/aDataFix_Project.git
cd aDataFix_Project

### 2. Vytvořte a aktivujte virtuální prostředí
python -m venv .venv
source .venv/bin/activate  # Na Windows použijte: .venv\Scripts\activate

### 3. Nainstalujte potřebné balíčky (závislosti)
pip install -r requirements.txt

### 4. Spusťte databázové migrace
Ujistěte se, že Vám na počítači běží lokální služba MySQL nebo MariaDB, a pak vytvořte potřebné tabulky příkazem:
python manage.py migrate

### 5. Spusťte vývojový server
python manage.py runserver

Nyní otevřete svůj oblíbený prohlížeč a přejděte na adresu http://127.0.0.1:8000/. Měla by se Vám zobrazit přihlašovací stránka!

---

## Struktura projektu

Pokud se potřebujete zorientovat v kódu, tady je rychlá mapa toho, kde co leží:

aDataFix-main/
├── manage.py
├── requirements.txt
├── aDataFix/                # Hlavní konfigurační složka projektu
│   ├── settings.py          # Nastavení projektu (DB, šablony, registrace aplikací)
│   ├── urls.py              # Hlavní směrování URL adres
│   └── aData_Fix/           # Jádro samotné aplikace (logika)
│       ├── views.py         # Pohledy aplikace (včetně db_login_view)
│       ├── models.py        # Databázové modely
│       ├── db_connector.py  # Vlastní správce připojení k databázi
│       └── templatetags/    # Vlastní filtry pro šablony (custom_filters.py)
└── templates/               # Globální složka pro HTML šablony
    └── aDataFix/
        └── db_login.html    # Hlavní přihlašovací stránka do databáze

---

##  Průvodce přihlášením do databáze

Jakmile se v prohlížeči dostanete na přihlašovací rozhraní, použijte pro připojení k databázi tyto údaje:

* Host: Zadejte 127.0.0.1, pokud Vám běží MariaDB/MySQL lokálně na Vašem PC, nebo zadejte IP adresu/doménu ostrého vzdáleného serveru.
* User: Pro lokální vývoj je to nejčastěji root, pro produkční server zadejte konkrétní uživatelské jméno vytvořené v MySQL.
* Password: Heslo, které patří k danému uživateli (např. Vaše root heslo do lokální MariaDB).
* Database Name: Zadejte název cílové databáze (např. divDB). Pokud si nejste jisti, vůbec to nevadí – databázi můžete kdykoliv vybrat nebo změnit později přímo v administraci aplikace.

---

## Technické poznámky

Abyste nemuseli ztrácet čas řešením chyb, tady je pár strukturálních rozhodnutí, která jsme v projektu udělali:

* Kompatibilita Python 3.14 & MySQL: Tradiční ovladače jako mysqlclient bývá na novějších verzích Pythonu velmi těžké zkompilovat. Abychom to vyřešili, používáme čistě pythonní knihovnu pymysql. Ta se automaticky injektuje jako alias za MySQLdb hned na startu uvnitř souboru aDataFix/__init__.py.
* Cesty k šablonám: Všechny HTML šablony jsou přehledně uložené v globální složce /templates v kořeni projektu. Django o nich ví díky upravenému nastavení DIRS v souboru settings.py.
* Registrace aplikace: Protože je naše aplikace vnořená, v settings.py je čistě zaregistrovaná pod svým plným názvem aDataFix.aData_Fix.

---
Ať se Vám s projektem skvěle pracuje! Pokud narazíte na nějaký zádrhel, neváhejte založit issue nebo napsat týmu.
