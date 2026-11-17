from django.urls import path, include, re_path
from . import views

from django.conf import settings
from django.contrib.auth import views as auth_views

__author__ = "Enrico Ferreguti"
__email__ = "enricofer@gmail.com"
__copyright__ = "Copyright 2017, Enrico Ferreguti"
__license__ = "GPL3"

urlpatterns = [
    re_path(r'^log/(\w+)/$', views.log, name='log'),
    re_path(r'^status/(\w+)/$', views.status, name='status'),
    re_path(r'^vlist/(\d+)/$', views.vlist, name='vlist'),
    re_path(r'^setextent/(\d+)/$', views.set_version_extent, name='set_version_extent'),
    re_path(r'^show/(\w+)/$', views.show, name='status'),
    re_path(r'^qgs/(\w+)/$', views.QGS_progetto, name='qgs'),
    re_path(r'^fix/(\w+)/$', views.fix, name='fix'),
    re_path(r'^basemaps/(background|foreground)/$', views.basemaps_js, name='basemaps'),
    re_path(r'^vparams/(\d+)/$', views.params_js, name='params_js'),
    re_path(r'^diff-view/(\w+)/$', views.diff_view, name='diffview'),
    re_path(r'^layer/(\w+)/(\w+)/(\w+)/$', views.vlayer, name='version_layer'),
    re_path(r'^vsummary/(\w+)/$', views.geojson_summary, name='geojson_summary'),
    re_path(r'^kart-api/(.*?)$', views.kart_api, name='kart_api'),
    re_path(r'^update/(\w+)/$', views.update, name='update'),
    re_path(r'^mvt/(?P<repo>\w+)/(?P<layer>\w+)/(?P<zoom>\d+)/(?P<x>\d+)/(?P<y>\d+).(?P<format>\w+)', views.mvt_view.as_view(), name='mvt'),
    re_path(r'^diff\/(?P<versione>\w+)\/(?P<hash>\w+)\/((?P<parent_hash>\w+)?\/)?$', views.diff, name='diff'),
    #path("accounts/", include("django.contrib.auth.urls")),
    #url(r'^diff/(?P<versione>\w+)/(?P<parent_hash>\w+)/(?P<parent_hash>\w+)/$', views.diff, name='diff'),
    #re_path(r'^login/', django.contrib.auth.views.LoginView),
    #re_path(r'^logout/', django.contrib.auth.views.LogoutView),
]