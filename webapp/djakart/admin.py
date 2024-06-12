from django.contrib.gis import admin
from django.shortcuts import render
from django.utils.html import format_html
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, Http404
from django_object_actions import DjangoObjectActions 
from django.template.response import TemplateResponse
from django import forms
from django.core.validators import FileExtensionValidator
from django.core.files import File
from io import StringIO
from django.core.files.base import ContentFile
from django.conf import settings

import json

import os
import re
import shutil
import uuid
from datetime import datetime
import xml.etree.ElementTree as ET

from .models import version, can_modify, modelli
from .kart_api import (
    crea_nuova_versione,
    elimina_versione, 
    crea_nuovo_repository,
    log_versione,
    merge_versione, 
    status_versione, 
    get_remote, 
    clone_versione,
    conflitti_versione,  
    undo_commit_versione,
    show_versione,
    restore_versione,
    commit_versione,
    pull_versione,
    kart_cmd
)

class importForm(forms.Form):
    nuovo_dataset = forms.FileField()
    #nuovo_dataset = forms.FileField()

    def __init__(self,*args,**kwargs):
        self.estensione = kwargs.pop('estensione')
        super().__init__(*args,**kwargs)
        self.fields['nuovo_dataset'] = forms.FileField(validators=[FileExtensionValidator(allowed_extensions=[self.estensione])])

    def clean(self):
        super().clean()
        nuovo_dataset = self.cleaned_data.get('username')

def handle_uploaded_file(f):
    fileAbsolutePath = os.path.join("/tmp/%s%s" % (uuid.uuid4().hex, os.path.splitext(f.name)[1]))
    with open(fileAbsolutePath, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)
    return fileAbsolutePath

class versioniAdmin(DjangoObjectActions, admin.GISModelAdmin):#admin.OSMGeoAdmin):

    change_form_template = 'admin/djakart/change_form.html'
    list_per_page = 50
    #modifiable = False
    #form = versioniForm
    #readonly_fields = ('mapping_service_url', 'log', 'status', 'mapa', 'get_project')
    list_display = ('nome','base','origine','merged','last_commit','note','progetto', )
    changelist_actions = ('aggiorna_cache', )
    change_actions = [
        'merge',
        'undo',
        'commit',
        'restore',
        'risolvi_conflitti',
        'annulla_merge',
        'conferma_merge',
        'aggiorna',
        'importa_geopackage',
        'importa_template',
        'esporta_geopackage',
        'nuova_versione_da_esistente'
    ]
    ordering = ['nome', ]

    def require_file(parameter,estensione):
        def decorator(func):
            def wrapper(modeladmin,request,obj,**kwargs):
                if not 'nuovo_dataset' in request.FILES:
                    request.current_app = modeladmin.admin_site.name
                    context = dict(
                        modeladmin.admin_site.each_context(request),
                        parameter = parameter,
                        form =  importForm(estensione = estensione),
                        title="Importa file"
                    )
                    return TemplateResponse(request, "admin/action_file.html", context)
                elif request.POST.get("confirmation") == "importa":
                    kwargs[parameter] = request.GET.get(parameter) 
                    form = importForm(request.POST,request.FILES, estensione = estensione)
                    if form.is_valid() and 'nuovo_dataset' in request.FILES:
                        dsfile = handle_uploaded_file(request.FILES['nuovo_dataset'])
                        kwargs[parameter] = dsfile
                        #obj.importa(dsfile)
                    else:
                        context = {
                            "parameter":  parameter,
                            "form": form,
                            "title": "Importa file"
                        }
                        return TemplateResponse(request, "admin/action_file.html", context)

                return func(modeladmin, request,obj, **kwargs)
                wrapper.__name__ = func.__name__
            return wrapper
        return decorator
    
    def require_confirmation(func):
        def wrapper(modeladmin, request, queryset):
            if request.GET.get("confirmation") is None:
                request.current_app = modeladmin.admin_site.name
                context = {"action":  request.path.split("/")[-2], "queryset": queryset}
                return TemplateResponse(request, "admin/action_confirmation.html", context)

            return func(modeladmin, request, queryset)

        wrapper.__name__ = func.__name__
        return wrapper

    def require_parameter(parameter):
        def decorator(func):
            def wrapper(modeladmin,request,obj,**kwargs):
                if request.GET.get(parameter) is None:
                    request.current_app = modeladmin.admin_site.name
                    context = {
                        "parameter":  parameter,
                        "value": "{} ".format(obj.nome)
                    }
                    return TemplateResponse(request, "admin/action_parameter.html", context)
                elif request.GET.get("confirmation") == "Commit":
                    kwargs[parameter] = request.GET.get(parameter) 

                return func(modeladmin, request,obj, **kwargs)
                wrapper.__name__ = func.__name__
            return wrapper
        return decorator

    def resolve_conflicts(func):
            def wrapper(modeladmin, request, obj, **kwargs):
                sj = json.loads(obj.status_(as_json=True))
                theirs = sj["kart.status/v2"]["merging"]["theirs"]
                #version_name = re.findall('(?<=Merging branch \")(.*)(?=\" into )',obj.status)[0]
                version_name = theirs.get("branch") or theirs.get("abbrevCommit")
                if request.GET.get('confirmation') is None:
                    request.current_app = modeladmin.admin_site.name
                    conflicts={}
                    conflitti_json = conflitti_versione(obj.nome)
                    for feat in conflitti_json["features"]:
                        conflict_id = ":".join(feat["id"].split(":")[0:-1])
                        if conflict_id in conflicts:
                            conflicts[conflict_id]["geojson"]["features"].append(feat)
                        else:
                            conflicts[conflict_id] = {
                                "conflict_id": conflict_id,
                                "geojson": {
                                  "type": "FeatureCollection",
                                  "features": [feat]
                                }
                            }

                    context = {
                        "conflicts":  json.dumps(conflicts), 
                        "root_wms":os.environ.get("QGIS_SERVER_EXTERNAL","qgis_server_external") + '?MAP=/kart_versions/', 
                        "base_name":obj.nome,
                        "version_name":version_name,
                        "continue": not conflicts
                    }
                    return TemplateResponse(request, "admin/resolve_conflicts.html", context)
                elif request.GET.get("confirmation") == "Risolvi i conflitti":
                    #kwargs['resolution'] = request.GET.get('resolution') 
                    for key,val in request.GET.items():
                        if not key in ('csrfmiddlewaretoken', 'confirmation'):
                            if val != "unresolved":
                                esito = obj.resolve(key,val)
                elif request.GET.get("confirmation") == "Completa Merge":
                    kart_cmd(obj.nome,["merge","--continue","-m", '"Completa merge di %s in %s"' % (version_name, obj.nome)])
                    obj.salva_cache()
                    version_obj = version.objects.get(nome=version_name)
                    version_obj.salva_cache()
                elif request.GET.get("confirmation") == "Risolvi i conflitti rinumerando la versione 'theirs'":
                    kart_cmd(obj.nome,["resolve","--renumber","theirs"])
                    obj.salva_cache()
                    version_obj = version.objects.get(nome=version_name)
                    version_obj.salva_cache()


                return func(modeladmin, request, obj, **kwargs)

            wrapper.__name__ = func.__name__
            return wrapper



    class Media:
        js = (
            "certificati/js/salva_stato_layers.js",
            "hp/js/scadenzario.js"
            #'repertorio/mappeDiBase.js',
            #'pua/pua_finestramappa.js',
        )
        css = {
             'all': ('pua/pua_finestramappa.css',)
        }

    def has_delete_permission(self, request, obj=None):
        if obj:
            return can_modify(request.user,obj)

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return ('clean','mapping_service_url', 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged')
        if can_modify(request.user,obj):
            return ('clean','mapping_service_url', 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged', 'nome', 'base')
        else:
            return ('clean','mapping_service_url', "template_qgis", 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged', 'referente', 'riservato', 'nome', 'base', 'origine')

    def get_fieldsets(self, request, obj=None):
        if obj:
            if obj.base:
                return (
                    ("intestazione", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('nome', ('base','merged','clean',),'note','get_project','mapping_service_url',('referente','riservato'),'mapa')
                    }),
                    ("rapporti", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('status', 'log',)
                    }),
                )
            else:
                return (
                    ("intestazione", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('nome', ('base','merged','clean',),'template_qgis','note','get_project','mapping_service_url',('referente','riservato'),'mapa')
                    }),
                    ("rapporti", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('status', 'log',)
                    }),
                )
        else:
            return (
                ("intestazione", {
                    'classes': ('grp-collapse grp-open',),
                    'fields': ('nome', 'base','template_qgis','note','referente','riservato')
                }),
            )


    def get_change_actions(self, request, object_id, form_url):

        obj = version.objects.get(pk=object_id)
        if obj.is_clean:
            if obj.base:
                if can_modify(request.user,obj.base):
                    if obj.is_merged_():
                        if can_modify(request.user,obj):
                            pre = ['importa_geopackage',]
                        else:
                            pre = []
                    else:
                        if can_modify(request.user,obj):
                            pre = ['merge','importa_geopackage',]
                        else:
                            pre = []
                else:
                    pre = []
            else:
                if can_modify(request.user,obj):
                    pre = ['importa_template', 'importa_geopackage', 'esporta_geopackage']
                else:
                    pre = []

            pre.append('nuova_versione_da_esistente')

            if can_modify(request.user,obj):
                return pre + ['undo','aggiorna']
            else:
                return pre + ['aggiorna']

        else:
            if can_modify(request.user,obj):
                pre = ['annulla_merge']
            else:
                pre = []
            if obj.is_faulty:
                return ['undo']
            if obj.has_conflicts_():
                return pre + ['risolvi_conflitti']
            if obj.is_merging_():
                return pre + ['annulla_merge','conferma_merge']
            else:
                return ['commit','restore']

    def aggiorna_cache(modeladmin, request, queryset):
        for v in queryset:
            v.salva_cache()

    def log(self,obj):
        if obj.pk:
            log_items = obj.log_json
            li_html = ""
            for item in log_items:
                li = '<li><a href="/djakart/diff/{versione}/{commit}/{parent}/" target="_blank">{abbrevCommit}</a></br>{message}</br>authored by {authorName} {commitTime}</br></li>'
                item["message"] = item["message"].replace("\n", "</br>")
                item["parent"] = item["parents"][0] if item["parents"] else ""
                item["authorName"]
                li_html += li.format(versione=obj.nome, **item)
                #print (li.format(versione=self.name, **item))
            html = "<ul>%s</ul>" % li_html
            return format_html(html)
        else:
            return "indeterminato"
    #log.allow_tags = True
    log.short_description = 'Log delle modifiche' 
    
    def status(self,obj):
        if obj.pk:
            
            if obj.is_clean:
                html = "<strong>Nessun cambiamento in sospeso</strong>"
            else:
                sj = json.loads(obj.status_(as_json=True))
                if sj["kart.status/v2"].get("conflicts"):
                    provenienza = sj["kart.status/v2"]["merging"]["theirs"]
                    html = '<strong>La versione {} è in fase di merge ed ha conflitti non riconciliati</strong>'.format( provenienza.get("branch") or provenienza.get("abbrevCommit") )
                elif obj.is_merging:
                    html = '<strong>La versione è in fase di merge</strong>'
                
                elif obj.cambiamenti_non_registrati and not obj.is_faulty:
                    html = '''
<strong>La versione ha dei cambiamenti non ancora registrati: 
    <a href="/djakart/diff/{versione}/HEAD/" target="_blank"> Verifica</a>
</strong> 
    '''.format(versione=obj.nome)
                else:
                    html = obj.status_()
            return format_html(html)
        else:
            return "indeterminato"
    #log.allow_tags = True
    status.short_description = 'Stato del repository'

    def mapa(self, obj):
        if obj.pk:
            html= '''<div id="map"></div><script>window.onload = loadFinestraMappa()</script>'''
            return format_html(html)
        else:
            return ''
    mapa.short_description = ''

    def get_project(self, obj):
        if obj.nome:
            html= '''<a href="/djakart/qgs/%s/" target="_blank"> Download</a>''' % obj.nome
            return format_html(html)
        else:
            return ''
    get_project.short_description = 'Progetto di QGIS'

    def merged(self, obj):
        return obj.is_merged
    merged.boolean = True  

    def clean(self, obj):
        return obj.is_clean
    clean.boolean = True  

    @require_confirmation
    def merge(self, request, obj):
        if obj.base:
            if obj.cambiamenti_non_registrati:
                raise ("OPERAZIONE DI MERGE NON CONSENTITA: La versione {} ha cambiamenti in sospeso".format(obj.nome))
            if obj.base.cambiamenti_non_registrati:
                raise ("OPERAZIONE DI MERGE NON CONSENTITA: La versione {} ha cambiamenti in sospeso".format(obj.base.nome))
            
            obj.base.config_user(request.user.username, request.user.email)
            obj.merge()
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.base.pk)
    
    @resolve_conflicts
    def risolvi_conflitti(self, request, obj):
        if obj.is_merging and not obj.has_conflicts:
            try:
                cmd = obj.merge(conferma=True)
            except Exception as E:
                print("KART EXCEPTION",E)
        return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_confirmation
    def annulla_merge(self, request, obj):
        if obj.pk:
            obj.merge(annulla=True)
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_confirmation
    def conferma_merge(self, request, obj):
        if obj.pk:
            obj.merge(conferma=True)
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_confirmation
    def aggiorna(self, request, obj):
        if obj.pk:
            obj.aggiorna()
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_confirmation
    def undo(self, request, obj):
        if obj.pk:
            obj.undo()
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    undo.short_description = "Annulla l'ultimo commit"
    
    @require_parameter("messaggio_di_registrazione")
    def commit(self, request, obj, **kwargs):
        if obj.pk:
            #print (kwargs["messaggio di registrazione"])
            obj.config_user(request.user.username,request.user.email)
            obj.commit("{}: {}".format(obj.nome, kwargs["messaggio_di_registrazione"]))
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
        
    @require_parameter("nome_nuova_versione")
    def nuova_versione_da_esistente(self, request, obj, **kwargs):
        if obj.pk:
            nuova_versione = version()
            nuova_versione.nome = kwargs["nome_nuova_versione"]
            nuova_versione.base = obj
            nuova_versione.save()
            return HttpResponseRedirect("/admin/djakart/version/%s/" % nuova_versione.pk)
            
    
    @require_file("importa_geopackage","gpkg")
    def importa_geopackage(self, request, obj, **kwargs):
        if obj.pk:
            obj.importa(kwargs["importa_geopackage"])
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
            
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_file("importa_template","qgs")
    def importa_template(self, request, obj, **kwargs):
        if obj.pk:
            with open(kwargs["importa_template"],"r") as template_file:
                template_source = template_file.read()
                template_root = ET.fromstring(template_source)
                prop_element = template_root.find("properties")

                if prop_element.find("Macros"):
                    prop_element.remove(prop_element.find("Macros"))

                macro_element = ET.SubElement(prop_element, "Macros")
                python_element = ET.SubElement(macro_element, "pythonCode")
                python_element.set("type", "QString")
                python_element.text = "{{ pythonmacro }}"
                template_source = ET.tostring(template_root,encoding='unicode')

                print (ET.tostring(prop_element,encoding='unicode'))
                
                custom_order_section = re.search('<custom-order enabled="0">((.|\n)*?)<\/custom-order>', template_source) 
                layer_items = re.finditer("<item>((.|\n)*?)<\/item>", custom_order_section.group()) 
                layer_ids = [lyr.group(1) for lyr in layer_items]

                template_source = re.sub("(?<=(table\=\&quot\;))(.+)(?=(\&quot;\.))", "{{ versione }}", template_source)
                template_source = re.sub("(?<=(table\=\"))(.+)(?=(\"\.))", "{{ versione }}", template_source)
                
                #template_filepath = os.path.join(settings.MEDIA_ROOT,"tmp",'%s.qgs' % uuid.uuid4().hex)
                #with open(template_filepath ,"w") as tf:
                #    tf.write(template_source)
                
                qgstmpl = modelli()
                qgstmpl.doc = ContentFile(template_source,"qgis_template.qgs")#File(StringIO(template_source),"qgis_template")
                qgstmpl.titolo = "VERSIONI_" + obj.nome
                qgstmpl.descrizione = json.dumps(layer_ids, indent=2)
                qgstmpl.abilitato = False
                qgstmpl.save()
                obj.template_qgis = qgstmpl
                obj.save()
            
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    
    @require_confirmation
    def restore(self, request, obj):
        if obj.pk:
            obj.restore()
            return HttpResponseRedirect("/admin/djakart/version/%s/" % obj.pk)
    restore.short_description = "Annulla le modifiche non registrate"

    def rigen_local_gpkg(self,obj):
        if not obj.base:
            target_name = obj.nome+"_export"
            target_path = os.path.join('/kart_versions', target_name) #settings.MEDIA_ROOT,
            gpkg_path = os.path.join(target_path, target_name + ".gpkg")
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            res = clone_versione (obj.nome, target_path)
            return gpkg_path

    def esporta_geopackage(self, request, obj):
        if obj.pk and not obj.base:
            response = FileResponse(open(self.rigen_local_gpkg(obj), 'rb'),content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="%s.gpkg"' % obj.nome
            return response

    #GDAL su rapper non supporta creazione di geodatabase esri
    def esporta_gdb(self, request, obj):
        if obj.pk and not obj.base:
            gpkg_loc = self.rigen_local_gpkg(obj)
            gdb_tmp = os.path.join("/tmp", uuid.uuid4().hex) #settings.MEDIA_ROOT, 

            response = FileResponse(open(self.rigen_local_gpkg(obj), 'rb'),content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="%s.gpkg"' % obj.nome
            return response


admin.site.register(version, versioniAdmin)
admin.site.register(modelli)