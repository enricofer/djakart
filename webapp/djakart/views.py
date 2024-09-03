from django.shortcuts import render
from django.template.loader import render_to_string
from django.template import Context, Template
from django.http import HttpResponseRedirect,JsonResponse,HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.views.decorators.csrf import csrf_exempt

from .models import version, writeQgs,basemap

from .kart_api import (
    log_versione,
    status_versione, 
    show_versione,
    _diff_view,
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
SRID = os.environ.get("REPO_CRS")
SRID_CODE = SRID.split(":")[1]

def is_member(user):
    return user.groups.filter(name=VERSIONI_USER_GROUP).exists()

# Create your views here.

def log(request,versione):
    obj = version.objects.get(nome=versione)
    jlog = log_versione(obj.nome,jsonoutput=True )
    print (type(jlog))
    return JsonResponse(jlog, safe=False)

def show(request,versione):
    obj = version.objects.get(nome=versione)
    jshow = show_versione(obj.nome,jsonoutput=True )
    return JsonResponse(jshow, safe=False)

def status(request,versione):
    obj = version.objects.get(nome=versione)
    status = status_versione(obj.nome)
    return render(request, 'log.html', {'log': status})

def diff(request,versione,hash,parent_hash=""):
    versione_obj = version.objects.get(nome=versione)
    diff = genera_diff_versione(versione,hash,parent_hash,crs=versione_obj.crs, extent=versione_obj.extent)
    print (diff)
    return HttpResponse(diff)

def diff_view(request,versione):
    versione_obj = version.objects.get(nome=versione)
    response =  HttpResponse(_diff_view(versione_obj.crs, versione_obj.extent))
    response['Content-Disposition'] = 'inline; filename="diff-view.html"'
    return response

def QGS_progetto(request,versione):
    versione_obj = version.objects.get(nome=versione)
    progetto = writeQgs(versione_obj)
    response = HttpResponse(progetto, content_type='application/xml')
    response['Content-Disposition'] = 'attachment; filename="%s.qgs"' % versione
    return response

def basemaps_js(request,depth):
    lyrsdef = basemap.getLyrs(depth)
    return HttpResponse(lyrsdef, content_type="text/javascript; charset=utf-8")

@login_required
@csrf_exempt
def set_version_extent(request, version_id):
    print ("version_id", version_id)
    res = "fail"
    versione_obj = version.objects.get(pk=version_id)
    if request.method == 'POST':
        extent = json.loads(request.body)["extent"]
        print ("extent",extent)
        versione_obj.extent = extent
        versione_obj.save()
        res = "ok"
    return JsonResponse({"result": res})

def vlist(request,versione_id):
    obj = version.objects.get(pk=versione_id)
    if obj.pk:
        evid = ""
        base_service = obj.base.mapping_service_url if obj.base else ""

        all_versions = [{
            "nome": "Versione corrente: " + obj.nome,
            "wms": obj.mapping_service_url,
        }]

        if obj.base:
            all_versions.append({
                "nome": "Base corrente: " + obj.base.nome,
                "wms": obj.base.mapping_service_url,
            })
            if obj.base != obj.origine:
                all_versions.append({
                    "nome": "Base origine: " + obj.origine.nome,
                    "wms": obj.origine.mapping_service_url,
                })
        else:
            all_versions.append({
                "nome": "",
                "wms": ""
            })

        for v in version.objects.all():
            if v.pk == obj.pk or (obj.base and v.pk == obj.base.pk) or (obj.origine and v.pk == obj.origine.pk):
                continue

            all_versions.append({
                "nome": v.nome,
                "wms": v.mapping_service_url,
            })
    else:
        all_versions = {}

    response = render(
        request, 
        'tutte_le_versioni.js',
        {'current_version': obj, 'vlist': json.dumps(all_versions)},
        content_type="text/javascript"
    )

    #response['Content-Disposition'] = 'attachment; filename="tutte_le_versioni.js"'

    return response



