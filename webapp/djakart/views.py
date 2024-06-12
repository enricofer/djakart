from django.shortcuts import render
from django.template.loader import render_to_string
from django.template import Context, Template
from django.http import HttpResponseRedirect,JsonResponse,HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required

from .models import version, writeQgs

from .kart_api import (
    log_versione,
    status_versione, 
    show_versione,
    commit_versione,
    genera_diff_versione,
    restore_versione,
    list_versioned_tables,
    geo_tables,
    KART_PGUSER,
    KART_PGUSER_PWD

) 

import uuid
import requests
import json
import re
import os
from xml.sax.saxutils import escape
from urllib.parse import quote,unquote,parse_qs

VERSIONI_USER_GROUP = "gis"

def is_member(user):
    return user.groups.filter(name=VERSIONI_USER_GROUP).exists()

# Create your views here.

def log(request,versione):
    obj = versioni.objects.get(nome=versione)
    jlog = log_versione(obj.nome,jsonoutput=True )
    print (type(jlog))
    return JsonResponse(jlog, safe=False)

def show(request,versione):
    obj = versioni.objects.get(nome=versione)
    jshow = show_versione(obj.nome,jsonoutput=True )
    return JsonResponse(jshow, safe=False)

def status(request,versione):
    obj = versioni.objects.get(nome=versione)
    status = status_versione(obj.nome)
    return render(request, 'log.html', {'log': status})

def diff(request,versione,hash,parent_hash=""):
    return HttpResponse(genera_diff_versione(versione,hash,parent_hash))

def QGS_progetto(request,versione):
    versione_obj = versioni.objects.get(nome=versione)
    progetto = writeQgs(versione_obj)
    response = HttpResponse(progetto, content_type='application/xml')
    response['Content-Disposition'] = 'attachment; filename="%s.qgs"' % versione
    return response

def vlist(request,versione_id):
    obj = versioni.objects.get(pk=versione_id)
    if obj.pk:
        evid = ""
        base_service = obj.base.mapping_service_url if obj.base else ""

        tutte_versioni = [{
            "nome": "Versione corrente: " + obj.nome,
            "wms": obj.mapping_service_url,
        }]

        if obj.base:
            tutte_versioni.append({
                "nome": "Base corrente: " + obj.base.nome,
                "wms": obj.base.mapping_service_url,
            })
            if obj.base != obj.origine:
                tutte_versioni.append({
                    "nome": "Base origine: " + obj.origine.nome,
                    "wms": obj.origine.mapping_service_url,
                })
        else:
            tutte_versioni.append({
                "nome": "BASE DBT SU OSCAR",
                "wms": "",
            })

        for v in versioni.objects.all():
            if v.pk == obj.pk or (obj.base and v.pk == obj.base.pk) or (obj.origine and v.pk == obj.origine.pk):
                continue
            
            tutte_versioni.append({
                "nome": v.nome,
                "wms": v.mapping_service_url,
            })
    else:
        tutte_versioni = {}
    
    return render(request, 'tutte_le_versioni.js', {'vlist': json.dumps(tutte_versioni)}, content_type="text/javascript")



