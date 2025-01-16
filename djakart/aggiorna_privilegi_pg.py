from versioni.models import versioni
from versioni.kart_api import grant_select_schema

import requests

for versione in versioni.objects.all():
    if not versione.base:
        pgschema = versione.nome+'_pub'
    else:
        pgschema = versione.nome
    
    grant_select_schema(pgschema)

    r = requests.get("http://10.10.21.50:8989/versioni/qgs/"+versione.nome)
    
    if r.status_code == 200:
        print ("aggiornamento privilegi versione ",versione.nome," OK!")
    else:
        print ("aggiornamento privilegi versione ",versione.nome," FAILED!")