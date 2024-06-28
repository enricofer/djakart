from django.contrib.gis.db import models
from django.utils.text import slugify
from django.db.models.signals import post_delete
from django.db.models import Q
from django.template.loader import render_to_string
from django.dispatch import receiver
from django.conf import settings
from datetime import datetime, timedelta
from django.template import Context, Template
from django.db.models import JSONField

from .kart_api import (
    KartException,
    crea_nuova_versione,
    elimina_versione, 
    crea_nuovo_repository,
    log_versione,
    merge_versione, 
    status_versione, 
    grant_select_schema, 
    resolve_conflitto,
    conflitti_versione,  
    undo_commit_versione,
    show_versione,
    restore_versione,
    commit_versione,
    pull_versione,
    merged_list_versione,
    kart_cmd,
    importa_dataset,
    aggiorna_riferimenti,
    config_user_versione,
    list_versioned_tables,
    geo_tables,
    KART_PGUSER,
    KART_PGUSER_PWD
) 

import os
import json
import uuid
import re
import requests
from xml.sax.saxutils import escape
from urllib.parse import quote,unquote,parse_qs

BASE_MAPPING_SERVICE = os.environ.get("QGIS_SERVER_EXTERNAL","qgis_server_external")
SRID = os.environ.get("REPO_CRS")
#SRID_CODE = SRID.split(":")[1]

def can_modify(u,v):
    return (v.riservato and u == v.referente) or not v.riservato or u.is_superuser

def writeQgs(versione_obj):
    versione_name = versione_obj.nome if versione_obj.base else "%s_pub" % versione_obj.nome
    versione_qgs_path = os.path.join("/kart_versions", versione_name+'.qgs')
    grant_select_schema(versione_name)
    progetto = getQgsProject(versione_obj)
    with open (versione_qgs_path,"w") as proqgs:
        proqgs.write(progetto)
    return progetto


def getQgsProject(versione_obj):
    versione_name = versione_obj.nome if versione_obj.base else "%s_pub" % versione_obj.nome
    template_obj = versione_obj.template_qgis or versione_obj.origine.template_qgis
    if template_obj:
        if versione_obj.base:
            with open (os.path.join(os.path.dirname(os.path.abspath(__file__)), "QGS_project_macro.py"), "r") as py: #
                macro = py.read()
        else:
            macro = ""
        with open (template_obj.doc.path, "r") as t:
            template_string = t.read()
        template_string = clean_ids(template_string, template_obj)

        template = Template(template_string)
        context = Context({
            "versione": versione_name,
            #"piano": versione_obj.piano if versione_obj.piano else "",
            "pythonmacro": escape(macro)
        })

        progetto = template.render(context)
        progetto = re.sub("(user='.*?('))", "user='%s'" % KART_PGUSER, progetto)
        progetto = re.sub("(password='.*?('))", "password='%s'" % KART_PGUSER_PWD, progetto)

    else:
        sources = []
        names = []
        temp_path = os.path.join("/", "tmp",'%s.qgs' % uuid.uuid4().hex)
        geo_tab = geo_tables(versione_obj.nome)
        vtab = list_versioned_tables(versione_obj.nome)
        for table in vtab:
            #if len(vtab) == 1 and table == 'md':
            #    continue
            table_pg_connection = {
                "host": os.environ.get("HOST_EXTERNAL", 'host_external'),
                "port": os.environ.get("POSTGRES_PORT_EXTERNAL", 'postgres_port_external'),
                "dbname": os.environ.get("VERSION_DB", 'version_db'),
                "user": os.environ.get("VERSION_VIEWER", 'version_viewer'),
                "password": os.environ.get("VERSION_VIEWER_PASSWORD", 'version_viewer_password'),
                "schema": versione_name,
                "table": table,
                "key_field": "auto_pk",
                "srid": versione_obj.crs,
            }
            if table in geo_tab:
                table_pg_connection["geom_field"] = "geom"
            datasource = '&'.join(['{key}={value}'.format(key=key,value=value) for key,value in table_pg_connection.items()])
            quoted_datasource = quote(datasource)
            sources.append(quoted_datasource)
            names.append(table)

        wms_params = {
            "qgs_path": temp_path ,
            "crs": versione_obj.crs,
            "sources": ";".join(sources),
            "names": ";".join(names)
        }

        wms_get_qgis_params = """
SERVICE=MAPCOMPOSITION&PROJECT={qgs_path}&
SOURCES={sources}&
NAMES={names}&
CRS={crs}&
GROUP=VERSION&
OVERWRITE=true""".format(**wms_params)
        wms_get_qgis_params = wms_get_qgis_params.replace("\n","")
        host = os.environ.get("QGIS_SERVER_EXTERNAL", '')
        r = requests.get(host, params=wms_get_qgis_params)
        if r.status_code == 200:
            progetto = r.text 
        else:
            progetto = "QGS project not found verify url:\n\n" + host + "?" + wms_get_qgis_params
    return progetto #xml

def clean_ids(qgs_string, modello):
    for layerid in json.loads(modello.descrizione):
        #layername = layerid.split("_")[0] + "_" + layerid.split("_")[1]
        layername = layerid[:-37]
        new_layerid = layername + "_" + str(uuid.uuid4())
        qgs_string = qgs_string.replace(layerid, new_layerid)
        #print (layerid, new_layerid)
    return qgs_string

def get_qgs_filename(project_name):
    path = "kart_versions/%s.qgs" % project_name
    return path

def cached(func):
    timecachedfuncs = ('status','has_conflicts','is_merging',)
    def wrapper(*args, **kwargs):
        versione = args[0]
        try:
            cached_props = versione.load_cache()
        except KartException: #fallback al commit più recente
            versione.undo(force=True)
            cached_props = versione.load_cache()
        if func.__name__ in cached_props.keys():
            if func.__name__ in timecachedfuncs:
                if versione.cache_timedelta() > 60:
                    print ("CACHE-MISS %s.%s cache_timedelta %s" % (versione, func.__name__,versione.cache_timedelta() ))
                    cached_props[func.__name__] = func(*args, **kwargs)
                else:
                    print ("CACHE-HIT %s.%s cache_timedelta %s" % (versione, func.__name__,versione.cache_timedelta() ))
        else:
            print ("CACHE-STORE %s.%s cache_timedelta %s" % (versione, func.__name__,versione.cache_timedelta() ))
            cached_props[func.__name__] = func(*args, **kwargs)
        return cached_props[func.__name__]
    return wrapper

class modelli(models.Model):

    def update_filename(self, filename):
        path = os.path.join('modelli/', "%s-%s" % (self.titolo, uuid.uuid4().hex))
        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, path)):
            os.makedirs(os.path.join(settings.MEDIA_ROOT, path))
        return os.path.join(path,filename)

    titolo = models.CharField(max_length=25)
    descrizione = models.TextField(blank=True,null=True,)
    doc = models.FileField(upload_to=update_filename,)

    def __str__(self):
        return "%d_%s" % (self.pk,self.titolo)

    class Meta:
        verbose_name_plural = "QGIS project templates"
        verbose_name = "QGIS project template"

class version(models.Model):

    class Meta:
        verbose_name_plural = "Versions"
        verbose_name = "Version"

    nome = models.CharField(verbose_name="Name", max_length=20)
    base = models.ForeignKey('version',blank=True,null=True, on_delete=models.PROTECT)
    versione_confronto = models.ForeignKey('version', related_name='confronto',blank=True,null=True, on_delete=models.PROTECT,verbose_name="compare version")
    note = models.TextField(blank=True)
    progetto = models.FileField(verbose_name="QGIS project", blank=True)
    extent = JSONField(default=[])
    crs = models.CharField(verbose_name="Coordinate system epsg code", default=SRID, max_length=20)
    template_qgis = models.ForeignKey('modelli', blank=True,null=True, on_delete=models.PROTECT, verbose_name='QGIS template', )
    referente = models.ForeignKey(settings.AUTH_USER_MODEL ,blank=True, null=True, on_delete=models.SET_NULL,limit_choices_to={'groups__name': 'gis'}, verbose_name="ownership", )
    riservato = models.BooleanField(verbose_name="reserved",default=False)

    def salva_cache(self, update=None):
        start = datetime.now()
        if os.path.exists(os.path.join('/kart_versions',self.nome+".json")):
            os.remove(os.path.join('/kart_versions',self.nome+".json"))
        if update:
            cache_dict=update
        else:
            cache_dict = {
                "pk": self.pk,
                "nome": self.nome,
                "base": self.base.nome if self.base else "",
                "origine": self.origine.nome if self.origine else "",
                "status": self.status_(),
                "is_merged": self.is_merged_(),
                "is_merging": self.is_merging_(),
                "has_conflicts": self.has_conflicts_(),
                "last_commit": self.last_commit_(),
                "log_json": self.log_json_(),
                "note": self.note,
                "progetto": self.progetto.path if self.progetto else "",
                "template": self.template_qgis.doc.path if self.template_qgis else "",
                "mapping_service_url": self.mapping_service_url,
                "delay": str(datetime.now()-start)
            }
        with open (os.path.join('/kart_versions',self.nome+".json"),"w") as cf:
            json.dump(cache_dict, cf) 
        return cache_dict

    def cache_timedelta(self):
        if os.path.exists(os.path.join('/kart_versions',self.nome+".json")):
            now = datetime.now()
            filetime =  datetime.fromtimestamp(os.path.getctime(os.path.join('/kart_versions',self.nome+".json")))
            filedelta = now - filetime
            return filedelta.total_seconds()
        else:
            return 9999999999999.9
    
    def load_cache(self):
        try:
            with open (os.path.join('/kart_versions',self.nome+".json"),"r") as cf:
                return json.load(cf) 
        except Exception as E:
            print (E)
            return self.salva_cache()

    @property
    def mapping_service_url(self):
        return BASE_MAPPING_SERVICE + "?MAP=%s" % self.publishing_path
    
    @property
    def project_path(self):
        if self.base:
            return self.progetto.path
    
    @property
    def publishing_path(self):
        if not self.base:
            path = os.path.join('/kart_versions',self.nome+"_pub.qgs")
        else:
            path = self.progetto.path.replace(settings.MEDIA_ROOT,"/")
        return path

    @property
    def origine(self):
        v = self
        while v.base:
            v = v.base
        return v

    @property
    def log(self):
        return log_versione(self.nome)
    
    @property
    @cached
    def log_json(self):
        return self.log_json_()
    
    def log_json_(self):
        return log_versione(self.nome, jsonoutput=True)
    
    @property
    @cached
    def status(self):
        return self.status_()
    
    def status_(self, as_json=False):
        return status_versione(self.nome, as_json=as_json)

    @property
    @cached
    def is_merging(self):
        return self.is_merging_()
    
    def is_merging_(self):
        s = self.status_(as_json=True)
        sj = json.loads(s)
        #return 'Repository is in "merging" state.' in s or "Merging branch" in s
        return sj["kart.status/v2"].get("state") == "merging"
    
    @property
    @cached
    def has_conflicts(self):
        return self.has_conflicts_()
    
    def has_conflicts_(self):
        #return self.is_merging_() and not 'No conflicts!' in self.status_()
        s = self.status_(as_json=True)
        sj = json.loads(s)
        return sj["kart.status/v2"].get("conflicts")

    @property
    def cambiamenti_non_registrati(self):
        return not self.is_clean

    @property
    @cached
    def is_clean(self):
        status = self.status
        return ("Nothing to commit, working copy clean" in status) or ("No working copy" in status)

    @property
    def is_faulty(self):
        return "exception" in self.status_()

    @property
    def show(self):
        return show_versione(self.nome)
    
    def merged_list(self):
        return merged_list_versione(self.nome)

    @property
    @cached
    def is_merged(self):
        return self.is_merged_()
    
    def is_empty(self):
        pass
        
    def is_merged_(self):
        log = self.log_json_()
        if self.base and log:
            last_commit_hash = log[0]["commit"]
            base_log_hash = [l["commit"] for l in self.base.log_json_()]
            return last_commit_hash in base_log_hash

    @property
    def conflitti(self):
        conflitti_versione(self.nome)

    @property
    @cached
    def last_commit(self):
        return self.last_commit_()

    def last_commit_(self):
        j = self.log_json_()
        if j:
            log = j[0]
        else:
            log = {
                "abbrevCommit": '---',
                "message": '---',
                "commitTime": '---',
            }
        return "{hash} - {mesg} - {date}".format(hash=log["abbrevCommit"], mesg=log["message"].replace("\n", " "), date=log["commitTime"][:10])

    def merge(self, annulla=False, conferma=False):
        merge_versione(self.nome, abort=annulla, confirm=conferma)
        self.salva_cache()
        if not conferma: # conferma va a lavorare solo sulla versione in cui si è effettuato il merge
            if self.base:
                self.base.salva_cache()
        #if not self.base:
        #    kart_cmd(self.base.nome+"_pub",["fetch","origin"])
        #    kart_cmd(self.base.nome+"_pub",["checkout","origin/main"])

    def aggiorna(self):
        pull_versione(self.nome)
        self.salva_cache()

    def undo(self, force=None):
        undo_commit_versione(self.nome, force=force)
        self.salva_cache()

    def restore(self):
        restore_versione(self.nome)

    def config_user(self,username,usermail):
        config_user_versione(self.nome,username,usermail)

    def commit(self,msg):
        commit_versione(self.nome,msg)
        self.salva_cache()

    def resolve(self,tag,risoluzione):
        resolve_conflitto(self.nome,tag,risoluzione)
    
    def aggiorna_progetto(self):
        writeQgs(self)
    
    def importa(self,dspath):
        ext = importa_dataset(self.nome, dspath, self.extent)
        self.extent = ext
        self.save()
        self.salva_cache()

    def save(self, *args, **kwargs):
        self.nome = slugify(self.nome).upper()
        if not self.pk is None:
            kwargs["update_fields"] = ['note','template_qgis','referente','riservato','extent']
        else:
            if self.riservato and not self.referente:
                self.riservato = False
            print ("BASE", self.base)
            if self.base:
                crea_nuova_versione(self.nome,self.base.nome)
                #crea progetto
                self.progetto = get_qgs_filename(self.nome)
                self.extent = self.base.extent
            else:
                crea_nuovo_repository(self.nome,bare=False,readonly_workingcopy=self.nome + "_pub")
                grant_select_schema(self.nome + "_pub")
                kart_cmd(self.nome,["import",  "-a", os.path.join(os.path.dirname(__file__),"prototipo.gpkg")]) #"--replace-existing",


        self.aggiorna_progetto()
        self.salva_cache()
        super().save(*args, **kwargs)

    def __str__(self):
        return "%s %s" % (self.nome,"(%s)" % self.base.nome if self.base else "")


@receiver(post_delete, sender=version)
def cancella_versioni(sender, instance, using, **kwargs):
    versione_path = instance.publishing_path
    json_path = os.path.join('/kart_versions',instance.nome+'.json')
    #shutil.rmtree(os.path.dirname(instance.progetto.path), ignore_errors=True)
    if not instance.base:
        nome = instance.nome
    else:
        nome =None
    elimina_versione(instance.nome)
    if os.path.exists(versione_path):
        os.remove(versione_path)
    if os.path.exists(json_path):
        os.remove(json_path)
    if nome:
        elimina_versione(instance.nome+"_export")
        elimina_versione(instance.nome+"_pub")
    
    #self.salva_cache()
        

OLTYPE_CHOICES = (
    ('WMS', 'WMS'),
    ('XYZ', 'XYZ'),
)

DEPTH_CHOICES = (
    ('background', 'background'),
    ('foreground', 'foreground'),
)

class basemap(models.Model):

    SERVICE_PARAMS_DEFAULT = {

    }

    REQUEST_PARAMS_DEFAULT = {
        "LAYERS": "",
        "DPI": 150,
        "CRS": ""
    }

    class Meta:
        verbose_name_plural = "Basemaps"
        verbose_name = "Basemap"

    name = models.CharField(max_length=20)
    oltype = models.CharField(max_length=4, choices=OLTYPE_CHOICES, default="WMS")
    srid = models.CharField(max_length=20)
    url = models.CharField(max_length=200)
    depth = models.CharField(max_length=10, choices=DEPTH_CHOICES, default="background")
    service_params = JSONField(default=SERVICE_PARAMS_DEFAULT,blank=True, null=True)
    request_params = JSONField(default=REQUEST_PARAMS_DEFAULT,blank=True, null=True)

    def __str__(self):
        return self.name
    
    @property
    def oldef(self):
        if self.oltype == "WMS":
            lyr_template = """
    new ol.layer.Tile({
                title: '%s',
                source: new ol.source.TileWMS({
                    url: '%s',
                    params: %s,
                    projection: '%s'
                })
                })"""
            
            return lyr_template % (
                self.name,
                self.url,
                str(self.request_params),
                self.srid,
            )
        elif self.oltype == "XYZ":
            if "tile.openstreetmap.org" in self.url:
                lyr_template = """
        new ol.layer.Tile({
                    title: '%s',
                    source: new ol.source.OSM()
                    })""" % self.name
            else:
                lyr_template = """
        new ol.layer.Tile({
                    title: '%s',
                    source: new ol.source.XYZ({
                        url: '%s',
                        projection: '%s'
                    })
                    })""" % (
                        self.name,
                        self.url,
                        self.srid,
                    )

            return lyr_template

    @staticmethod
    def getLyrs(depth):
        if depth not in dict(DEPTH_CHOICES):
            return ""
        
        lyrsdef = "function get%sLyrs() {return [" % depth.capitalize()
        for bm in basemap.objects.filter(depth=depth):
            lyrsdef += bm.oldef
            lyrsdef += ',\n'
        lyrsdef += ']}\n'
        return lyrsdef