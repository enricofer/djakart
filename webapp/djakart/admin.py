from django.contrib.gis import admin
from django.shortcuts import render
from django.utils.html import format_html
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, Http404
from django_object_actions import DjangoObjectActions, action
from django.template.response import TemplateResponse
from django import forms
from django.core.validators import FileExtensionValidator
from django.core.files import File
from io import StringIO
from django.conf import settings

import json

import subprocess
import os
import re
import shutil
import uuid
from datetime import datetime

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from .models import version, can_modify, modelli, basemap
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
#SRID = os.environ.get("REPO_CRS")
#SRID_CODE = SRID.split(":")[1]

OGR2OGR = "/usr/bin/ogr2ogr"

SITE_SUBPATH = os.environ.get("SITE_SUBPATH","")

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
    list_display = ('nome','base','origine','merged','archiviato','last_commit','note','progetto', )
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
        'esporta',
        'archivia_versione',
        'nuova_versione_da_esistente'
    ]
    ordering = ['nome', ]

    def change_view(self, request, object_id, **kwargs):
        obj = version.objects.get(pk=object_id)
        if not "extra_context" in kwargs:
            kwargs["extra_context"] = {}
        kwargs["extra_context"]['crs'] = obj.crs.split(":")[1]
        kwargs["extra_context"]['site_subpath'] = SITE_SUBPATH
        return super(versioniAdmin, self).change_view(request, object_id, **kwargs) #, extra_context=extra_context

    def require_file(parameter,estensione):
        def decorator(func):
            def wrapper(modeladmin,request,obj,**kwargs):
                if not 'nuovo_dataset' in request.FILES:
                    request.current_app = modeladmin.admin_site.name
                    context = dict(
                        modeladmin.admin_site.each_context(request),
                        parameter = parameter,
                        form =  importForm(estensione = estensione),
                        title="Import file"
                    )
                    return TemplateResponse(request, "admin/action_file.html", context)
                elif request.POST.get("confirmation") == "import":
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
                            "title": "Import file"
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

    def require_parameter(parameter,choices=None):
        def decorator(func):
            def wrapper(modeladmin,request,obj,**kwargs):
                if request.GET.get(parameter) is None:
                    request.current_app = modeladmin.admin_site.name
                    context = {
                        "parameter":  parameter,
                        "choices": choices,
                        "value": "{} - ".format(obj.nome)
                    }
                    return TemplateResponse(request, "admin/action_parameter.html", context)
                elif request.GET.get("confirmation") == "Invia":
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
                    conflitti_json = conflitti_versione(obj.nome, obj.crs)
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
                        "crs": obj.crs,
                        "crscode": obj.crs.split(":")[-1],
                        "root_wms":os.environ.get("QGIS_SERVER_EXTERNAL","qgis_server_external") + '?MAP=/kart_versions/', 
                        "base_name":obj.nome,
                        "version_name":version_name,
                        "version_id": obj.pk,
                        "continue": not conflicts,
                        "site_subpath": SITE_SUBPATH or "",
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
        )
        css = {
        }

    def has_delete_permission(self, request, obj=None):
        if obj:
            return can_modify(request.user,obj)

    def get_readonly_fields(self, request, obj=None):
        if not obj:
            return ('clean','mapping_service_url', 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged', 'get_summary')
        if can_modify(request.user,obj):
            return ('apply_map_extent', 'clean','mapping_service_url', 'crs', 'base_diff', 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged', 'nome', 'base', 'get_summary', 'archiviato')#, 'entry_commit'
        else:
            return ('clean','mapping_service_url', "template_qgis", 'crs', 'base_diff', 'log', 'last_commit', 'status', 'mapa', 'get_project', 'merged', 'referente', 'riservato', 'nome', 'base', 'origine', 'get_summary', 'archiviato')#, 'entry_commit'

    def get_fieldsets(self, request, obj=None):
        if obj:
            if obj.base:
                if obj.archiviato:
                    return (
                        ("intestazione", {
                            'classes': ('grp-collapse grp-open',),
                            'fields': ('nome', ('base','merged','archiviato',),'note','mapa',)
                        }),
                        ("rapporti", {
                            'classes': ('grp-collapse grp-open',),
                            'fields': ('log',)
                        }),
                    )
                
                else:
                    return (
                        ("intestazione", {
                            'classes': ('grp-collapse grp-open',),
                            'fields': ('nome', ('base','merged','clean','archiviato'),'template_qgis','note','get_project','mapping_service_url',('referente','riservato'),'mapa',('crs','extent','apply_map_extent'))
                        }),
                        ("rapporti", {
                            'classes': ('grp-collapse grp-open',),
                            'fields': ('status', ('entry_commit', 'get_summary'), 'base_diff', 'log',)
                        }),
                    )
            else:
                return (
                    ("intestazione", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('nome', ('base','merged','clean',), 'reserved_ids','template_qgis','note','get_project','mapping_service_url',('referente','riservato'),'mapa',('crs','extent','apply_map_extent'))
                    }),
                    ("rapporti", {
                        'classes': ('grp-collapse grp-open',),
                        'fields': ('status', 'get_summary', 'base_diff', 'log',)
                    }),
                )
        else:
            return (
                ("intestazione", {
                    'classes': ('grp-collapse grp-open',),
                    'fields': ('nome', 'base','reserved_ids','template_qgis','crs','note','referente','riservato')
                }),
            )


    def get_change_actions(self, request, object_id, form_url):

        obj = version.objects.get(pk=object_id)
        if obj.archiviato:
            return []
        if obj.is_clean:
            if obj.base:
                if can_modify(request.user,obj.base):
                    if obj.is_merged_():
                        if can_modify(request.user,obj):
                            pre = ['importa_template','importa_geopackage',]
                        else:
                            pre = []
                    else:
                        if can_modify(request.user,obj):
                            pre = ['merge','importa_geopackage',]
                        else:
                            pre = []
                    if obj.is_merged and not obj.archiviato:
                        pre.append('archivia_versione')
                else:
                    pre = []
            else:
                if can_modify(request.user,obj):
                    pre = ['importa_template', 'importa_geopackage', 'esporta']
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
    
    @action(label="Archive version", description="Archive version")
    @require_confirmation
    def archivia_versione(self, request, obj):
        obj.archivia_versione()

    def base_diff(self,obj):
        if obj.pk:
            if obj.archiviato:
                return "archived version"
            diff_html = '<select id="version-source-diff" class="form-select">'
            log_items = obj.log_json
            options_html = ''
            for item in log_items:
                options_html += '<option value="{commit}">{abbrevCommit} {message}</option>'.format(**item)
            #diff_html += '{options}</select><select id="versioni-target-diff" class="form-select"><option value="" disabled selected hidden>Scegliere un commit...</option>{options}</select><a onclick="generaDiff(\'{versione}\')" target="_blank">Genera diff</a>'.format(versione=obj.nome,options=options_html)
            if obj.entry_commit:
                diff_html += '<option value="{entrypoint}">Entrypoint from entry commit ({abbrev})</option>'.format(entrypoint=obj.entry_commit, abbrev=obj.entry_commit[0:7])
            if obj.base:
                entry = obj.entrypoint
                diff_html += '<option value="{entrypoint}">Entrypoint from base ({abbrev})</option>'.format(entrypoint=entry, abbrev=entry[0:7])
            diff_html += '<option value="PARENT" disabled selected>Previous commit</option>{options}</select>'.format(options=options_html)
            return format_html(diff_html)
        else:
            return "undetermined"
    base_diff.short_description = 'Commit base for diffs' 

    def log(self,obj):
        if obj.pk:
            log_items = obj.log_json
            li_html = ""
            for item in log_items:
                li = '<li><a href="#" onclick="generateDiff(\'{subpath}\',\'{versione}\',\'{commit}\',\'\');event.preventDefault();" target="_blank">{abbrevCommit}</a></br>{message}</br>authored by {authorName} {commitTime}</br></li>'
                item["message"] = item["message"].replace("\n", "</br>")
                item["versione"] = obj.base.nome if (obj.archiviato and obj.base) else obj.nome
                li_html += li.format(subpath=SITE_SUBPATH, **item)
            html = "<ul>%s</ul>" % li_html
            return format_html(html)
        else:
            return "undetermined"
    log.short_description = 'Commits log' 
    
    def status(self,obj):
        if obj.pk:
            
            if obj.is_clean:
                html = "<strong>No pending changes</strong>"
            else:
                sj = json.loads(obj.status_(as_json=True))
                if sj["kart.status/v2"].get("conflicts"):
                    provenienza = sj["kart.status/v2"]["merging"]["theirs"]
                    html = '<strong>The version{} is merging and has conflicted changes</strong>'.format( provenienza.get("branch") or provenienza.get("abbrevCommit") )
                elif obj.is_merging:
                    html = '<strong>The Version is merging</strong>'
                
                elif obj.cambiamenti_non_registrati and not obj.is_faulty:
                    html = '''
<strong>The current version has not committed edits: 
    <a href="{site_subpath}/djakart/diff/{versione}/HEAD/" target="_blank"> Verify</a><a href="{site_subpath}/djakart/version/{versione}/actions/commit/" target="_blank"> Commit</a>
</strong> 
    '''.format(site_subpath=SITE_SUBPATH, versione=obj.nome)
                else:
                    html = obj.status_()
            return format_html(html)
        else:
            return "indeterminato"
    #log.allow_tags = True
    status.short_description = 'Repository State'

    def mapa(self, obj):
        if obj.pk:
            params = '{'
            if obj.archiviato:
                params += 'archiviato: true,'
            if os.path.exists("/kart_versions/{}.geojson".format(obj.nome)):
                params += 'polyJSON: "{}",'.format(SITE_SUBPATH + '/djakart/vsummary/{}/'.format(obj.nome))
            params += '}'
            return format_html('''<div id="map"></div><script>window.onload = loadFinestraMappa()</script>''')
        else:
            return ''
    mapa.short_description = ''

    def get_summary(self, obj):
        if obj.nome:
            html= '''<a href="%s/djakart/vsummary/%s/" target="_blank"> Download GeoJSON summary</a>''' % (SITE_SUBPATH, obj.nome)
            return format_html(html)
        else:
            return ''
    get_summary.short_description = 'GeoJSON Summary'

    def get_project(self, obj):
        if obj.nome:
            html= '''<a href="%s/djakart/qgs/%s/" target="_blank"> Download</a>''' % (SITE_SUBPATH, obj.nome)
            return format_html(html)
        else:
            return ''
    get_project.short_description = 'QGIS Project'

    def merged(self, obj):
        return obj.is_merged
    merged.boolean = True  

    def clean(self, obj):
        return obj.is_clean
    clean.boolean = True  

    def apply_map_extent(self, obj):
        link = '''<a href="#" class="button" onclick="apply_map_extension();event.preventDefault();" >Apply map extension</a>'''
        return format_html(link)
    apply_map_extent.short_description = ''

    @action(label="Merge to base repository", description="Merge to base repository")
    @require_confirmation
    def merge(self, request, obj):
        if obj.base:
            if obj.cambiamenti_non_registrati:
                raise ("OPERAZIONE DI MERGE NON CONSENTITA: La versione {} ha cambiamenti in sospeso".format(obj.nome))
            if obj.base.cambiamenti_non_registrati:
                raise ("OPERAZIONE DI MERGE NON CONSENTITA: La versione {} ha cambiamenti in sospeso".format(obj.base.nome))
            
            obj.base.config_user(request.user.username or "user_name_config_needed", request.user.email or "user_email_config@needed.org")
            obj.merge()
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.base.pk))
    
    @action(label="Reconcile conflicts", description="Reconcile conflicting edits")
    @resolve_conflicts
    def risolvi_conflitti(self, request, obj):
        if obj.is_merging and not obj.has_conflicts:
            try:
                cmd = obj.merge(conferma=True)
            except Exception as E:
                print("KART EXCEPTION",E)
        return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    risolvi_conflitti.short_description = 'reconcile conflicts'
    
    @action(label="Undo merge", description="Refuse conflicted merge")
    @require_confirmation
    def annulla_merge(self, request, obj):
        if obj.pk:
            obj.merge(annulla=True)
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="Apply merge", description="Apply reconciled merge")
    @require_confirmation
    def conferma_merge(self, request, obj):
        if obj.pk:
            obj.merge(conferma=True)
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="Update", description="Update status cache")
    @require_confirmation
    def aggiorna(self, request, obj):
        if obj.pk:
            obj.aggiorna()
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="Undo last commit", description="Go back one step in edits log")
    @require_confirmation
    def undo(self, request, obj):
        if obj.pk:
            obj.undo()
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="Commit", description="Record edits as a commit")
    @require_parameter("Commit message")
    def commit(self, request, obj, **kwargs):
        if obj.pk:
            #print (kwargs["messaggio di registrazione"])
            obj.config_user(request.user.username,request.user.email)
            obj.commit("{}: {} ".format(obj.nome, kwargs["Commit message"]))
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="New sub-version", description="New version from the existing one")
    @require_parameter("New version name")
    def nuova_versione_da_esistente(self, request, obj, **kwargs):
        if obj.pk:
            nuova_versione = version()
            nuova_versione.nome = kwargs["New version name"]
            nuova_versione.base = obj
            nuova_versione.crs = obj.crs
            nuova_versione.save()
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, nuova_versione.pk))
            
    @action(label="Import geopackage", description="Import all tables from geopackage and commit to repository")
    @require_file("importa_geopackage","gpkg")
    def importa_geopackage(self, request, obj, **kwargs):
        if obj.pk:
            obj.importa(kwargs["importa_geopackage"])
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
        
    @action(label="Import QGIS template", description="Import a QGS project as base template for repository (allows RW on tables)")
    @require_file("importa_template","qgs")
    def importa_template(self, request, obj, **kwargs):
        if obj.pk:
            obj.import_template(kwargs["importa_template"])
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))
    
    @action(label="Reset not commited edits", description="Reset not commited edits")
    @require_confirmation
    def restore(self, request, obj):
        if obj.pk:
            obj.restore()
            return HttpResponseRedirect("%s/admin/djakart/version/%s/" % (SITE_SUBPATH, obj.pk))

    def rigen_local_gpkg(self,obj):
        if not obj.base:
            target_name = obj.nome+"_export"
            target_path = os.path.join('/kart_versions', target_name) #settings.MEDIA_ROOT,
            gpkg_path = os.path.join(target_path, target_name + ".gpkg")
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            res = clone_versione (obj.nome, target_path)
            return gpkg_path

    
    def ex_esporta_geopackage(self, request, obj):
        if obj.pk and not obj.base:
            response = FileResponse(open(self.rigen_local_gpkg(obj), 'rb'),content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="%s.gpkg"' % obj.nome
            return response

    #GDAL su rapper non supporta creazione di geodatabase esri
    def ex_esporta_gdb(self, request, obj):
        if obj.pk and not obj.base:
            gpkg_loc = self.rigen_local_gpkg(obj)
            gdb_tmp = os.path.join("/tmp", uuid.uuid4().hex) #settings.MEDIA_ROOT, 

            response = FileResponse(open(self.rigen_local_gpkg(obj), 'rb'),content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="%s.gpkg"' % obj.nome
            return response
        
    @action(label="Export repository", description="Export repository as GeoPackage, Shapefiles or Esri Geodatabase")
    @require_parameter("Formato_di_esportazione", ["Geopackage", "Shapefiles"]) #, "GeoDataBase" (not supported on current GDAL)
    def esporta(self, request, obj, **kwargs):
        if obj.pk:
            if kwargs["Formato_di_esportazione"] == "Geopackage":
                return self.esporta_geopackage(request, obj)
            if kwargs["Formato_di_esportazione"] == "Shapefiles":
                return self.esporta_shp(request, obj)
            if kwargs["Formato_di_esportazione"] == "GeoDataBase":
                return self.esporta_gdb(request, obj)

    def esporta_geopackage(self, request, obj):
        if obj.pk:# and not obj.base:
            response = FileResponse(open(self.rigen_local_gpkg(obj), 'rb'),content_type='application/octet-stream')
            response['Content-Disposition'] = 'attachment; filename="%s.gpkg"' % obj.nome
            return response

    def esporta_gdb(self, request, obj):
        if obj.pk:# and not obj.base:
            return self.zip_and_response(obj, "OpenFileGDB")

    def esporta_shp(self, request, obj):
        if obj.pk:# and not obj.base:
            return self.zip_and_response(obj, "ESRI Shapefile")
    
    def zip_and_response(self, obj, format):

        if format == 'ESRI Shapefile':
            ext = '.shp'
        elif format == 'OpenFileGDB':
            ext = '.gdb'

        gpkg_loc = self.rigen_local_gpkg(obj)
        dir_tmp = os.path.join(settings.MEDIA_ROOT, "tmp", uuid.uuid4().hex + ext)
        if format in ('ESRI Shapefile', ): #'OpenFileGDB'):
            os.mkdir(dir_tmp)

        subprocess.run([OGR2OGR, '-skipfailures', '-f', format, dir_tmp, gpkg_loc])

        zipMemory = BytesIO()
        zip = ZipFile(zipMemory, 'w', ZIP_DEFLATED)

        #for filename in os.listdir(dir_tmp):
        #    print (filename)
        #    zip.write(os.path.join(dir_tmp,filename),filename)
        #    os.remove(os.path.join(dir_tmp,filename))
        
        for root, directories, files in os.walk(dir_tmp):
            for file in files:
                file_path = os.path.join(root, file)
                archive_path = os.path.relpath(file_path, dir_tmp)
                zip.write(file_path, archive_path)
                os.remove(file_path)

        for root, directories, files in os.walk(dir_tmp):
            for dir in directories:
                os.rmdir(os.path.join(root, dir))
        
        os.rmdir(dir_tmp)

        # fix for Linux zip files read in Windows
        for filename in zip.filelist:
            filename.create_system = 0

        zip.close()
        zipMemory.seek(0)

        response = FileResponse(zipMemory,content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="%s%s.zip"' % (obj.nome,ext)
        return response


admin.site.register(version, versioniAdmin)

class templateAdmin(DjangoObjectActions, admin.GISModelAdmin):

    model = modelli
    readonly_fields = ['descrizione', ]

    def has_add_permission(self, request, obj=None):
        return False

admin.site.register(modelli, templateAdmin)
admin.site.register(basemap)

admin.site.site_title = 'Djakart administration'
admin.site.site_header = 'Djakart'
admin.site.index_title = 'Site administration'